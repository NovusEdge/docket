#!/usr/bin/env python3
"""Explicitly migrate a schema-1 Docket JSONL ledger to schema 2.

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
exclusive-create semantics.  The repository's ``lib.docket_ledger``
``validate_entries`` function is authoritative.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable


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
    "kind", "state", "text",
    "scope", "rationale", "depends_on", "evidence", "revisit",
    "cost_if_wrong", "cost", "pinned", "choice", "alternatives",
    "id", "ts", "author", "session", "branch", "decided_by", *RELATION_FIELDS,
}
SCHEMA_LATEST = 2

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
        if raw.get("schema") == SCHEMA_LATEST:
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
    raw: dict[str, Any], old_id: str, entry: dict[str, Any],
    kinds: dict[str, str], notes: list[str] | None,
) -> None:
    """Move a supersedes target that derives to a question onto answers.

    A question cannot carry answers (lib.docket_ledger forbids it), so a
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
    raw: dict[str, Any], old_id: str, entry: dict[str, Any],
    kinds: dict[str, str], notes: list[str] | None,
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
    source: list[dict[str, Any]], notes: list[str] | None = None,
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
        detail = "; ".join(
            f"{state}: {', '.join(ids)}" for state, ids in sorted(unknown.items())
        )
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
        raise MigrationError("malformed mapping: top-level value must be an object keyed by old IDs")
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
    if all(isinstance(group, list) and group and all(isinstance(item, str) for item in group)
           for group in value):
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
    if field in {"ts", "author", "session", "branch", "decided_by", "rationale", "revisit", "cost_if_wrong"}:
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


def build_records(source: list[dict[str, Any]], mapping: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
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
            if "depends_on" in entry else []
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
            "cost_if_wrong": entry.get("cost_if_wrong", entry.get("cost", raw.get("cost_if_wrong", ""))),
            "pinned": _metadata(raw, entry, "pinned", False),
        }
        if not isinstance(record["cost_if_wrong"], str):
            raise MigrationError(f"metadata cost_if_wrong for {old_id} must be a string")
        if entry["kind"] == "decision":
            choice = entry.get("choice", answer)
            if not isinstance(choice, str) or not choice:
                raise MigrationError(f"decision mapping for {old_id} requires non-empty choice")
            alternatives = entry.get("alternatives", [choice])
            if not isinstance(alternatives, list) or not all(isinstance(item, str) and item for item in alternatives):
                raise MigrationError(f"decision mapping for {old_id} alternatives must be a list of strings")
            record["choice"] = choice
            record["alternatives"] = list(dict.fromkeys([*alternatives, choice]))
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
            "overrides": sorted(field for field in (*RELATION_FIELDS, "depends_on") if field in entry),
        }
        record["legacy"] = {"source_id": old_id, "raw": raw, "relation_map": relation_map}
        output.append(record)
    return output


def core_validator() -> Callable[[list[dict[str, Any]]], Any]:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        core = importlib.import_module("lib.docket_ledger")
    except (ImportError, ModuleNotFoundError) as exc:
        raise MigrationError("cannot import lib.docket_ledger.validate_entries") from exc
    candidate = getattr(core, "validate_entries", None)
    if not callable(candidate):
        raise MigrationError("lib.docket_ledger.validate_entries is unavailable")
    return candidate


def migrate(source_path: Path | str, mapping_path: Path | str, output_path: Path | str,
            validator: Callable[[list[dict[str, Any]]], Any] | None = None) -> None:
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


STEPS = {1: build_records}

BACKUP_SUFFIX = ".schema1"
TEMP_SUFFIX = ".migrating"


def _report_line(old_id: str, record: dict[str, Any]) -> str:
    return f"{old_id} -> {record['id']} {record['kind']}/{record['state']}"


def migrate_in_place(path: Path | str, mapping_path: Path | str | None = None,
                     dry_run: bool = False) -> tuple[int, list[str], list[str]]:
    """Convert a ledger to the current schema, keeping the original beside it.

    Both renames happen inside one directory, so each is atomic. A crash
    between them leaves the source at BACKUP_SUFFIX and the result at
    TEMP_SUFFIX, and neither file is truncated.
    """
    path = Path(path)
    backup = Path(str(path) + BACKUP_SUFFIX)
    temp = Path(str(path) + TEMP_SUFFIX)

    source = read_source(path)
    version = detect_version(source)
    if version == SCHEMA_LATEST:
        return 0, [], []
    step = STEPS.get(version)
    if step is None:
        raise MigrationError(f"no migration from schema {version} to {SCHEMA_LATEST}")

    # Checked only once a conversion is actually needed: a ledger already at
    # schema 2 must exit clean even if an earlier migration left a backup.
    if not dry_run and backup.exists():
        raise MigrationError(
            f"{backup} already exists; a second migration would overwrite the original"
        )

    old_ids = {raw["id"] for raw in source}
    notes: list[str] = []
    if mapping_path is None:
        mapping = derive_mapping(source, notes=notes)
    else:
        mapping = read_mapping(Path(mapping_path), old_ids)
    records = step(source, mapping)
    records = core_validator()(records) or records
    report = [_report_line(raw["id"], record) for raw, record in zip(source, records)]
    if dry_run:
        return len(records), report, notes

    # This module loads as top-level "docket_migrate" under bin/docket (only
    # lib/ on sys.path) and as "lib.docket_migrate" under the test suite (the
    # repo root on sys.path). A module-level import cannot satisfy both, so
    # core_validator's own root-plus-package-name approach is reused here.
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    ledger_lock = importlib.import_module("lib.docket_ledger").ledger_lock
    with ledger_lock(path):
        if temp.exists():
            raise MigrationError(f"{temp} already exists; remove it and retry")
        with temp.open("x", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        path.rename(backup)
        temp.rename(path)
    return len(records), report, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("source", type=Path, help="schema-1 JSONL source ledger")
    parser.add_argument("--map", dest="mapping", required=True, type=Path,
                        help="explicit JSON classification map")
    parser.add_argument("--output", required=True, type=Path,
                        help="new schema-2 JSONL destination; must not exist")
    args = parser.parse_args(argv)
    try:
        migrate(args.source, args.mapping, args.output)
    except (MigrationError, ValueError) as exc:
        print(f"migrate_ledger: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
