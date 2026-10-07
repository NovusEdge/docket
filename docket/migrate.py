#!/usr/bin/env python3
"""Explicitly migrate a Docket JSONL ledger to the current schema.

Schema 1 becomes schema 2 through the classification map described below. Schema 2
becomes schema 3 by renumbering each kind from 1 (docket.rebase.renumber_per_kind).

The classification map is a JSON object keyed by every source ID.  Each map
value must contain ``kind``, ``state``, and ``text`` and may contain any typed
record metadata plus relation overrides.  Relation override values use source
IDs, so the tool can audit exactly what was reinterpreted:

    {
      "d17": {
        "kind": "decision", "state": "adopted", "text": "...",
        "choice": "...", "supports": [["d10"]], "answers": ["d15"],
        "supersedes": []
      }
    }

Omitted ``supports`` translates the old ``because`` field.  Omitted
``supersedes`` translates the old field.  Supplying an override, including an
empty list, is an explicit treatment and is retained in ``legacy`` audit
metadata.  IDs default to the kind prefix plus the numeric suffix of the old
ID (``d17`` becomes ``c17``, ``d17``, or ``q17``).

This module deliberately has no prose classifier.  It validates all source
references and all mapped records before opening the destination with
exclusive-create semantics.  The repository's ``docket.ledger``
``validate_entries`` function is authoritative.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from docket import feature_archive, features
from docket.ledger import ledger_lock, project, validate_entries
from docket.ledger import read as read_ledger
from docket.rebase import ProseChange, RebaseError, renumber_per_kind

OLD_ID = re.compile(r"^d[1-9][0-9]*$")
NEW_ID = re.compile(r"^[cdq][1-9][0-9]*$")
KINDS = {"claim", "decision", "question"}
STATES = {
    "claim": {"unassessed", "accepted", "disputed", "rejected"},
    "decision": {"adopted", "revoked"},
    "question": {"open", "resolved"},
}
PREFIX = {"claim": "c", "decision": "d", "question": "q"}
RELATION_FIELDS = ("supports", "answers", "supersedes")
OPTIONAL_FIELDS = {
    "kind",
    "state",
    "text",
    "scope",
    "rationale",
    "depends_on",
    "evidence",
    "revisit",
    "cost_if_wrong",
    "cost",
    "pinned",
    "choice",
    "alternatives",
    "id",
    "ts",
    "author",
    "session",
    "branch",
    "decided_by",
    *RELATION_FIELDS,
}
SCHEMA_LATEST = 3

# Schema 1 typed the difference between settling on doing something and
# settling on not doing it. Schema 2 does not, and the choice text carries it.
# ruled-out must not become revoked: a non-adopted decision renders as
# unavailable current support, and these records still apply.
LEGACY_STATES = {
    "settled": ("decision", "adopted"),
    "ruled-out": ("decision", "adopted"),
    "open": ("question", "open"),
}


class MigrationError(ValueError):
    """An input, map, relation, or destination contract error."""


def _json_object(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MigrationError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MigrationError(f"malformed {label} JSON: line {exc.lineno}: {exc.msg}") from exc


def read_source(path: Path) -> list[dict[str, Any]]:
    """Read and structurally validate every non-empty JSONL source line."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MigrationError(f"cannot read source {path}: {exc}") from exc
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MigrationError(f"malformed input at line {lineno}: {exc.msg}") from exc
        if not isinstance(raw, dict):
            raise MigrationError(f"malformed input at line {lineno}: record must be an object")
        old_id = raw.get("id")
        if isinstance(raw.get("schema"), int) and raw["schema"] >= 2:
            records.append(raw)
            continue
        if not isinstance(old_id, str) or not OLD_ID.fullmatch(old_id):
            raise MigrationError(f"malformed input at line {lineno}: invalid old id {old_id!r}")
        if old_id in seen:
            raise MigrationError(f"malformed input at line {lineno}: duplicate id {old_id}")
        seen.add(old_id)
        _source_relations(raw, old_id)
        records.append(raw)
    return records


def detect_version(records: list[dict[str, Any]]) -> int:
    """The schema version every record in the source shares.

    A record with no schema field is schema 1. Schema 1 wrote no such field.
    """
    versions = {record.get("schema", 1) for record in records}
    if not versions:
        return SCHEMA_LATEST
    if len(versions) > 1:
        found = ", ".join(str(value) for value in sorted(versions, key=str))
        raise MigrationError(f"mixed schema versions in one ledger: {found}")
    version = versions.pop()
    if not isinstance(version, int):
        raise MigrationError(f"invalid schema version {version!r}")
    return version


def _rewrite_supersedes_into_answers(
    raw: dict[str, Any],
    old_id: str,
    entry: dict[str, Any],
    kinds: dict[str, str],
    notes: list[str] | None,
) -> None:
    """Move a supersedes target that derives to a question onto answers.

    A question cannot carry answers (docket.ledger forbids it), so a
    question source is left on the default supersedes path; same-kind
    question-to-question supersession is already legal there.
    """
    if entry["kind"] == "question":
        return
    targets = _id_list(raw.get("supersedes", []), f"{old_id}.supersedes")
    moved = [ref for ref in targets if kinds.get(ref) == "question"]
    if not moved:
        return
    entry["supersedes"] = [ref for ref in targets if ref not in moved]
    entry["answers"] = [*entry.get("answers", []), *moved]
    if notes is not None:
        for ref in moved:
            notes.append(f"{old_id} supersedes {ref}, a question; recorded as an answers edge")


def _rewrite_support_into_questions(
    raw: dict[str, Any],
    old_id: str,
    entry: dict[str, Any],
    kinds: dict[str, str],
    notes: list[str] | None,
) -> None:
    """Drop a because target that derives to a question from supports.

    Schema 2 has no relation a question can hold on the justifying end:
    supports and depends_on both refuse a question target. The source edge
    survives regardless, in legacy.relation_map.source_because.
    """
    groups = _support_sets(raw.get("because", []), f"{old_id}.because")
    filtered: list[list[str]] = []
    changed = False
    for group in groups:
        kept = [ref for ref in group if kinds.get(ref) != "question"]
        if len(kept) != len(group):
            changed = True
            if notes is not None:
                for ref in group:
                    if ref not in kept:
                        notes.append(
                            f"{old_id} is justified by {ref}, a question; support edge "
                            "dropped and kept in legacy.relation_map.source_because"
                        )
        if kept:
            filtered.append(kept)
    if changed:
        entry["supports"] = filtered


def derive_mapping(
    source: list[dict[str, Any]],
    notes: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build a classification map from schema-1 fields alone.

    Every value reads a field or the record's structure. Nothing reads the
    meaning of an English sentence, so the tool still has no prose classifier.
    """
    unknown: dict[str, list[str]] = {}
    mapping: dict[str, dict[str, Any]] = {}
    for raw in source:
        old_id = raw["id"]
        state = raw.get("state")
        if not isinstance(state, str) or state not in LEGACY_STATES:
            unknown.setdefault(str(state), []).append(old_id)
            continue
        kind, new_state = LEGACY_STATES[state]
        answer = raw.get("answer", "")
        if not isinstance(answer, str):
            raise MigrationError(f"answer for {old_id} must be a string")
        text = raw.get("question", "")
        entry: dict[str, Any] = {"kind": kind, "state": new_state, "text": text}
        if kind == "decision":
            if not answer:
                raise MigrationError(
                    f"{old_id} is {state} with an empty answer, so no choice can be derived"
                )
            entry["choice"] = answer
        mapping[old_id] = entry
    if unknown:
        detail = "; ".join(f"{state}: {', '.join(ids)}" for state, ids in sorted(unknown.items()))
        raise MigrationError(f"unrecognised schema-1 state(s) {detail}")

    # Kinds are resolved for every record before either rule runs, so a rule
    # can tell a question target from a claim or decision target.
    kinds = {old_id: entry["kind"] for old_id, entry in mapping.items()}
    for raw in source:
        old_id = raw["id"]
        entry = mapping[old_id]
        _rewrite_supersedes_into_answers(raw, old_id, entry, kinds, notes)
        _rewrite_support_into_questions(raw, old_id, entry, kinds, notes)
    return mapping


def read_mapping(path: Path, source_ids: set[str]) -> dict[str, dict[str, Any]]:
    value = _json_object(path, "mapping")
    if not isinstance(value, dict):
        raise MigrationError(
            "malformed mapping: top-level value must be an object keyed by old IDs"
        )
    missing = sorted(source_ids - set(value))
    if missing:
        raise MigrationError(f"missing mapping for old id(s): {', '.join(missing)}")
    extra = sorted(set(value) - source_ids)
    if extra:
        raise MigrationError(f"mapping contains unknown old id(s): {', '.join(extra)}")
    result: dict[str, dict[str, Any]] = {}
    for old_id in sorted(source_ids, key=_old_sort_key):
        entry = value[old_id]
        if not isinstance(entry, dict):
            raise MigrationError(f"malformed mapping for {old_id}: value must be an object")
        missing_fields = [field for field in ("kind", "state", "text") if field not in entry]
        if missing_fields:
            raise MigrationError(f"mapping for {old_id} is missing {', '.join(missing_fields)}")
        unknown = sorted(set(entry) - OPTIONAL_FIELDS)
        if unknown:
            raise MigrationError(f"mapping for {old_id} has unknown field(s): {', '.join(unknown)}")
        kind = entry["kind"]
        state = entry["state"]
        text = entry["text"]
        if not isinstance(kind, str) or kind not in KINDS:
            raise MigrationError(f"mapping for {old_id} has invalid kind {kind!r}")
        if not isinstance(state, str) or state not in STATES[kind]:
            raise MigrationError(f"mapping for {old_id} has invalid state {state!r} for {kind}")
        if not isinstance(text, str) or not text:
            raise MigrationError(f"mapping for {old_id} must have non-empty text")
        result[old_id] = entry
    return result


def _old_sort_key(value: str) -> int:
    return int(value[1:])


def _source_relations(raw: dict[str, Any], old_id: str) -> tuple[list[list[str]], list[str]]:
    supports = _support_sets(raw.get("because", []), f"{old_id}.because")
    supersedes = _id_list(raw.get("supersedes", []), f"{old_id}.supersedes")
    return supports, supersedes


def _support_sets(value: Any, label: str) -> list[list[str]]:
    if value is None or value == []:
        return []
    if not isinstance(value, list):
        raise MigrationError(f"malformed input relation {label}: expected a list")
    if all(isinstance(item, str) for item in value):
        return [list(value)]
    if all(
        isinstance(group, list) and group and all(isinstance(item, str) for item in group)
        for group in value
    ):
        return [list(group) for group in value]
    raise MigrationError(f"malformed input relation {label}: expected IDs or ID lists")


def _id_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise MigrationError(f"malformed input relation {label}: expected a list of IDs")
    return list(value)


def _check_refs(groups: list[list[str]], known: set[str], label: str) -> None:
    for group in groups:
        for ref in group:
            if ref not in known:
                raise MigrationError(f"unknown reference {ref} in {label}")


def _mapped_id(old_id: str, entry: dict[str, Any]) -> str:
    candidate = entry.get("id", f"{PREFIX[entry['kind']]}{old_id[1:]}")
    if not isinstance(candidate, str) or not NEW_ID.fullmatch(candidate):
        raise MigrationError(f"mapping for {old_id} has invalid typed id {candidate!r}")
    if candidate[0] != PREFIX[entry["kind"]]:
        raise MigrationError(f"mapping for {old_id}: id prefix does not match kind {entry['kind']}")
    return candidate


def _map_supports(value: Any, old_id: str, known: set[str]) -> list[list[str]]:
    groups = _support_sets(value, f"mapping for {old_id}.supports")
    _check_refs(groups, known, f"mapping for {old_id}.supports")
    return groups


def _map_ids(value: Any, old_id: str, field: str, known: set[str]) -> list[str]:
    ids = _id_list(value, f"mapping for {old_id}.{field}")
    _check_refs([ids], known, f"mapping for {old_id}.{field}")
    return ids


def _metadata(raw: dict[str, Any], entry: dict[str, Any], field: str, default: Any) -> Any:
    value = entry.get(field, raw.get(field, default))
    if field in {
        "ts",
        "author",
        "session",
        "branch",
        "decided_by",
        "rationale",
        "revisit",
        "cost_if_wrong",
    }:
        if not isinstance(value, str):
            raise MigrationError(f"metadata {field} for {raw['id']} must be a string")
    if field == "scope":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise MigrationError(f"metadata scope for {raw['id']} must be a list of strings")
    if field == "depends_on":
        value = _id_list(value, f"mapping for {raw['id']}.depends_on")
    if field == "evidence":
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise MigrationError(f"metadata evidence for {raw['id']} must be a list of objects")
    if field == "pinned" and not isinstance(value, bool):
        raise MigrationError(f"metadata pinned for {raw['id']} must be boolean")
    return value


def build_records(
    source: list[dict[str, Any]], mapping: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    known = {raw["id"] for raw in source}
    ids = {old_id: _mapped_id(old_id, mapping[old_id]) for old_id in known}
    if len(set(ids.values())) != len(ids):
        raise MigrationError("mapping produces duplicate typed IDs")
    output: list[dict[str, Any]] = []
    for raw in source:
        old_id = raw["id"]
        entry = mapping[old_id]
        source_supports, source_supersedes = _source_relations(raw, old_id)
        if "supports" in entry:
            supports_old = _map_supports(entry["supports"], old_id, known)
        else:
            _check_refs(source_supports, known, f"{old_id}.because")
            supports_old = source_supports
            for ref in (ref for group in supports_old for ref in group):
                if mapping[ref]["kind"] not in {"claim", "decision"}:
                    raise MigrationError(
                        f"support reference {old_id}->{ref} crosses into a question; "
                        "provide an explicit supports override"
                    )
        if "answers" in entry:
            answers_old = _map_ids(entry["answers"], old_id, "answers", known)
        else:
            answers_old = []
        if "supersedes" in entry:
            supersedes_old = _map_ids(entry["supersedes"], old_id, "supersedes", known)
        else:
            supersedes_old = source_supersedes
            _check_refs([supersedes_old], known, f"{old_id}.supersedes")
        for target in source_supersedes:
            if mapping[target]["kind"] != entry["kind"]:
                # A cross-kind supersession cannot be translated implicitly.
                # It may be explicitly retired, remapped to a same-kind
                # target, or (when the target is a question) represented as
                # an answer relation.  Core validation checks answer targets.
                if "supersedes" not in entry:
                    raise MigrationError(
                        f"cross-kind supersession {old_id}->{target} requires an explicit "
                        "supersedes override"
                    )
        supports = [[ids[ref] for ref in group] for group in supports_old]
        depends_on_old = (
            _map_ids(entry["depends_on"], old_id, "depends_on", known)
            if "depends_on" in entry
            else []
        )
        depends_on = [ids[ref] for ref in depends_on_old]
        answers = [ids[ref] for ref in answers_old]
        supersedes = [ids[ref] for ref in supersedes_old]
        answer = raw.get("answer", "")
        if not isinstance(answer, str):
            raise MigrationError(f"malformed input: answer for {old_id} must be a string")
        rationale = _metadata(raw, entry, "rationale", answer)
        record: dict[str, Any] = {
            "schema": 2,
            "kind": entry["kind"],
            "id": ids[old_id],
            "text": entry["text"],
            "state": entry["state"],
            "ts": _metadata(raw, entry, "ts", ""),
            "author": _metadata(raw, entry, "author", ""),
            "session": _metadata(raw, entry, "session", ""),
            "branch": _metadata(raw, entry, "branch", ""),
            "scope": _metadata(raw, entry, "scope", []),
            "rationale": rationale,
            "supports": supports,
            "depends_on": depends_on,
            "answers": answers,
            "supersedes": supersedes,
            "evidence": _metadata(raw, entry, "evidence", []),
            "revisit": _metadata(raw, entry, "revisit", ""),
            "cost_if_wrong": entry.get(
                "cost_if_wrong", entry.get("cost", raw.get("cost_if_wrong", ""))
            ),
            "pinned": _metadata(raw, entry, "pinned", False),
        }
        if not isinstance(record["cost_if_wrong"], str):
            raise MigrationError(f"metadata cost_if_wrong for {old_id} must be a string")
        if entry["kind"] == "decision":
            choice = entry.get("choice", answer)
            if not isinstance(choice, str) or not choice:
                raise MigrationError(f"decision mapping for {old_id} requires non-empty choice")
            alternatives = entry.get("alternatives", [])
            if not isinstance(alternatives, list) or not all(
                isinstance(item, str) and item for item in alternatives
            ):
                raise MigrationError(
                    f"decision mapping for {old_id} alternatives must be a list of strings"
                )
            record["choice"] = choice
            # The choice is no longer folded in. A schema 1 ledger records no
            # alternatives, and a list holding only the choice says nothing.
            record["alternatives"] = [
                item for item in dict.fromkeys(alternatives) if item != choice
            ]
            record["decided_by"] = _metadata(raw, entry, "decided_by", "")
        elif "decided_by" in entry:
            raise MigrationError(f"decided_by is decision-only for {old_id}")
        relation_map = {
            "source_because": raw.get("because", []),
            "source_depends_on": raw.get("depends_on", []),
            "source_answers": raw.get("answers", []),
            "source_supersedes": raw.get("supersedes", []),
            "mapped_supports": supports,
            "mapped_depends_on": depends_on,
            "mapped_answers": answers,
            "mapped_supersedes": supersedes,
            "overrides": sorted(
                field for field in (*RELATION_FIELDS, "depends_on") if field in entry
            ),
        }
        record["legacy"] = {"source_id": old_id, "raw": raw, "relation_map": relation_map}
        output.append(record)
    return output


def core_validator() -> Callable[[list[dict[str, Any]]], Any]:
    """Validate schema-2 records as the schema-3 ledger they would become.

    Returns None, so migrate() keeps the schema-2 records it was given.
    """

    def check(records: list[dict[str, Any]]) -> None:
        validate_entries(renumber_step(records)[0])

    return check


def migrate(
    source_path: Path | str,
    mapping_path: Path | str,
    output_path: Path | str,
    validator: Callable[[list[dict[str, Any]]], Any] | None = None,
) -> None:
    source_path, mapping_path, output_path = map(Path, (source_path, mapping_path, output_path))
    if output_path.exists():
        raise MigrationError(f"output already exists: {output_path}")
    source = read_source(source_path)
    mapping = read_mapping(mapping_path, {raw["id"] for raw in source})
    records = build_records(source, mapping)
    validated = (validator or core_validator())(records)
    if isinstance(validated, list):
        records = validated
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise MigrationError(f"output already exists: {output_path}") from exc
    except OSError as exc:
        raise MigrationError(f"cannot create output {output_path}: {exc}") from exc


def renumber_step(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], list[ProseChange]]:
    """Schema 2 to 3: per-kind ids, with schema 3 stamped on every line."""
    renumbered, mapping, prose_changes = renumber_per_kind(records)
    return [{**record, "schema": SCHEMA_LATEST} for record in renumbered], mapping, prose_changes


STEPS = {1: build_records, 2: renumber_step}

BACKUP_SUFFIX = ".schema"
TEMP_SUFFIX = ".migrating"


@dataclass
class MigrationResult:
    count: int
    report: list[str]
    notes: list[str]
    mapping: dict[str, str]
    per_kind: dict[str, int]
    prose_changes: list[ProseChange]
    features_events: int = 0
    rewritten: list[str] = field(default_factory=list)
    rewrite_counts: dict[str, int] = field(default_factory=dict)
    backup: str = ""


def _report_line(old_id: str, record: dict[str, Any]) -> str:
    # Correction and review lines carry no state.
    state = record.get("state")
    return f"{old_id} -> {record['id']} {record['kind']}" + (f"/{state}" if state else "")


def _run_step(
    version: int,
    records: list[dict[str, Any]],
    mapping_path: Path | str | None,
    notes: list[str],
) -> tuple[list[dict[str, Any]], dict[str, str], list[ProseChange]]:
    if version != 1:
        try:
            return STEPS[version](records)
        except RebaseError as exc:
            raise MigrationError(
                f"cannot renumber this ledger: {exc}; run docket check and repair it first"
            ) from exc
    # The classification map exists only for schema 1: it assigns the kinds that
    # schema never recorded. Every later step is mechanical.
    if mapping_path is None:
        classes = derive_mapping(records, notes=notes)
    else:
        classes = read_mapping(Path(mapping_path), {raw["id"] for raw in records})
    return STEPS[1](records, classes), {}, []


def _feature_files(ledger_path: Path) -> list[Path]:
    store = ledger_path.parent / "features.jsonl"
    found = [store] if store.exists() else []
    return found + sorted(feature_archive.archive_dir_for(store).glob("features-*.jsonl"))


def _read_events(path: Path) -> list[dict[str, Any]]:
    """Raw events, unvalidated: features.read refuses the schema this step upgrades."""
    events: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise MigrationError(f"{path}: line {number}: invalid JSON: {exc.msg}") from exc
    return events


def _migrated_map(records: list[dict[str, Any]]) -> dict[str, str]:
    """Old id to new id, from the ledger's own ``migrated_from``.

    An old id held by two records is left out: a merge from a schema-2 branch
    can give one old id to a record on each side, and guessing would point an
    event at the wrong one. ``docket check`` reports the id it leaves behind.
    """
    held: dict[str, list[str]] = {}
    for record in records:
        if record.get("migrated_from"):
            held.setdefault(record["migrated_from"], []).append(record["id"])
    return {old: ids[0] for old, ids in held.items() if len(ids) == 1}


def _remap_features(
    ledger_path: Path, mapping: dict[str, str], records: list[dict[str, Any]]
) -> list[tuple[Path, list[dict[str, Any]]]]:
    """Every features file still at schema 1, with its events remapped.

    A file at schema 2 was rewritten by an earlier run that died before the
    ledger swap; its ids are already new, and mapping them again would send
    each to a different record.
    """
    by_id = {entry["id"]: entry for entry in project(records, validated=True)}
    pending = []
    for target in _feature_files(ledger_path):
        events = _read_events(target)
        if any(event.get("schema") == 1 for event in events):
            pending.append((target, features.remap_events(events, mapping, by_id)))
    return pending


def _events_text(events: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in events)


def _write_synced(temp: Path, text: str) -> None:
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _check_backup(path: Path, backup: Path) -> None:
    """Refuse a backup that is not a copy of the ledger being migrated.

    An identical one is what a crashed run leaves behind, and the rerun accepts it.
    """
    if backup.exists() and backup.read_bytes() != path.read_bytes():
        raise MigrationError(
            f"{backup} already exists and differs from {path}; a second migration "
            "would overwrite the original"
        )


def _link_backup(path: Path, backup: Path) -> None:
    try:
        os.link(path, backup)
    except FileExistsError:
        _check_backup(path, backup)
    except OSError:
        # No hard links on this filesystem. Copy through a temp so a crash
        # cannot leave a half-written backup that the next run would refuse.
        staging = backup.with_name(backup.name + TEMP_SUFFIX)
        shutil.copyfile(path, staging)
        os.replace(staging, backup)


def _commit(
    path: Path,
    backup: Path,
    records: list[dict[str, Any]] | None,
    remap: Callable[[], list[tuple[Path, list[dict[str, Any]]]]],
    extra: tuple[tuple[Path, str], ...] = (),
) -> int:
    """Write every file the migration touches. Returns the features events rewritten.

    Ledger lock, then the features lock. Every temp is written and fsynced
    before the first rename, so a failure while writing leaves nothing moved.
    Features and ``extra`` files go first; the ledger goes last, as a
    hard-linked backup and then one os.replace, so a crash anywhere leaves the
    ledger at its old schema and a rerun repeats the work, skipping the
    features files that already moved. ``records`` is None when the ledger is
    already current and only features files move.
    """
    store = path.parent / "features.jsonl"
    temp = Path(str(path) + TEMP_SUFFIX)
    with ExitStack() as locks:
        locks.enter_context(ledger_lock(path))
        if store.exists():
            locks.enter_context(ledger_lock(store))
        pending = remap()
        staged = [
            (target.with_name(target.name + TEMP_SUFFIX), target, _events_text(events))
            for target, events in pending
        ]
        staged += [(t.with_name(t.name + TEMP_SUFFIX), t, text) for t, text in extra]
        temps = [staging for staging, _, _ in staged] + ([temp] if records is not None else [])
        try:
            for staging, _, text in staged:
                _write_synced(staging, text)
            if records is not None:
                _write_synced(
                    temp,
                    "".join(
                        json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records
                    ),
                )
        except BaseException:
            for stale in temps:
                stale.unlink(missing_ok=True)
            raise
        for staging, target, _ in staged:
            os.replace(staging, target)
        if records is not None:
            _link_backup(path, backup)
            os.replace(temp, path)
    return sum(len(events) for _, events in pending)


def migrate_in_place(
    path: Path | str,
    mapping_path: Path | str | None = None,
    dry_run: bool = False,
    rewrite: Sequence[Path | str] = (),
) -> MigrationResult:
    """Convert a ledger to the current schema, keeping the original beside it.

    Every step runs in memory before anything is written, so a failure at any
    version leaves the ledger as it was. The backup is named after the starting
    schema. The features store and archives move with the ledger; see ``_commit``
    for the write order and what a crash leaves behind. A ledger already current
    still gets its features files remapped when they are at schema 1.
    """
    path = Path(path)

    source = read_source(path)
    version = detect_version(source)
    backup = Path(f"{path}{BACKUP_SUFFIX}{version}")
    if version == SCHEMA_LATEST:
        result = MigrationResult(0, [], [], {}, {}, [])
        records = read_ledger(path, lock=False)
        mapping = _migrated_map(records)
        if dry_run:
            pending = _remap_features(path, mapping, records)
            result.features_events = sum(len(events) for _, events in pending)
        else:
            result.features_events = _commit(
                path, backup, None, lambda: _remap_features(path, mapping, records)
            )
        return result
    if version not in STEPS:
        raise MigrationError(f"no migration from schema {version} to {SCHEMA_LATEST}")
    if mapping_path is not None and version != 1:
        raise MigrationError(
            f"a classification map applies only to schema 1; this ledger is schema {version}"
        )

    # Checked only once a conversion is actually needed: a ledger already at
    # the latest schema must exit clean even if an earlier migration left a backup.
    if not dry_run:
        _check_backup(path, backup)

    notes: list[str] = []
    records = source
    renumbered: dict[str, str] = {}
    prose_changes: list[ProseChange] = []
    for current in range(version, SCHEMA_LATEST):
        records, renumbered, prose_changes = _run_step(current, records, mapping_path, notes)
    records = validate_entries(records)
    result = MigrationResult(
        count=len(records),
        report=[_report_line(raw["id"], record) for raw, record in zip(source, records)],
        notes=notes,
        mapping=renumbered,
        per_kind={kind: sum(r["kind"] == kind for r in records) for kind in PREFIX},
        prose_changes=prose_changes,
        backup=str(backup),
    )
    if dry_run:
        pending = _remap_features(path, renumbered, records)
        result.features_events = sum(len(events) for _, events in pending)
        return result

    result.features_events = _commit(
        path, backup, records, lambda: _remap_features(path, renumbered, records)
    )
    return result
