"""Typed, append-only JSONL ledger primitives.

The module deliberately has no dependency on the command line interface.  It
is also the single validation boundary for records read from disk and records
about to be appended, so callers cannot accidentally treat a damaged ledger
as a partially valid one.
"""

from __future__ import annotations

import copy
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = 2
KINDS = ("claim", "decision", "question")
STATES = {
    "claim": ("unassessed", "accepted", "disputed", "rejected"),
    "decision": ("adopted", "revoked"),
    "question": ("open", "resolved"),
}
ID_RE = re.compile(r"([cdq])(0|[1-9][0-9]*)$")
COMMON_DEFAULTS: dict[str, Any] = {
    "scope": [],
    "rationale": "",
    "supports": [],
    "depends_on": [],
    "answers": [],
    "supersedes": [],
    "evidence": [],
    "revisit": "",
    "cost_if_wrong": "",
    "pinned": False,
}
COMMON_FIELDS = frozenset({"schema", "kind", "id", "text", "state", "ts", "author", "session", "branch", *COMMON_DEFAULTS})
DECISION_FIELDS = frozenset({"choice", "alternatives", "decided_by"})
AUDIT_FIELDS = frozenset({"legacy"})
ALLOWED_FIELDS = COMMON_FIELDS | DECISION_FIELDS | AUDIT_FIELDS


class LedgerError(ValueError):
    """A human-actionable schema, reference, or storage error."""


def _error(where: str, message: str) -> LedgerError:
    return LedgerError(f"docket: {where}: {message}")


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _copy_defaults(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    for key, value in COMMON_DEFAULTS.items():
        result.setdefault(key, copy.deepcopy(value))
    return result


def make_record(
    kind: str,
    text: str,
    *,
    state: str | None = None,
    choice: str | None = None,
    alternatives: list[str] | None = None,
    scope: list[str] | None = None,
    rationale: str = "",
    supports: list[list[str]] | None = None,
    depends_on: list[str] | None = None,
    answers: list[str] | None = None,
    supersedes: list[str] | None = None,
    evidence: list[dict[str, str]] | None = None,
    revisit: str = "",
    cost_if_wrong: str = "",
    pinned: bool = False,
    author: str = "unknown",
    session: str = "",
    branch: str = "",
    decided_by: str | None = None,
    ts: str | None = None,
    record_id: str | None = None,
) -> dict[str, Any]:
    """Build an unnumbered or explicitly numbered schema 2 record."""
    if kind not in KINDS:
        raise _error("record", f"unknown kind {kind!r}; expected claim, decision, or question")
    if not isinstance(text, str) or not text.strip():
        raise _error("record", "text must be a non-empty string")
    if state is None:
        state = {"claim": "unassessed", "decision": "adopted", "question": "open"}[kind]
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "kind": kind,
        "id": record_id if record_id is not None else "",
        "text": text,
        "state": state,
        "ts": ts if ts is not None else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "author": author,
        "session": session,
        "branch": branch,
        "scope": scope if scope is not None else [],
        "rationale": rationale,
        "supports": supports if supports is not None else [],
        "depends_on": depends_on if depends_on is not None else [],
        "answers": answers if answers is not None else [],
        "supersedes": supersedes if supersedes is not None else [],
        "evidence": evidence if evidence is not None else [],
        "revisit": revisit,
        "cost_if_wrong": cost_if_wrong,
        "pinned": pinned,
    }
    if kind == "decision":
        if alternatives is not None and not isinstance(alternatives, list):
            raise _error("record", "alternatives must be a list")
        if choice is not None and not isinstance(choice, str):
            raise _error("record", "choice must be a string")
        record["choice"] = choice if choice is not None else ""
        record["alternatives"] = alternatives.copy() if isinstance(alternatives, list) else (alternatives if alternatives is not None else [])
        if choice and choice not in record["alternatives"]:
            record["alternatives"].insert(0, choice)
        record["decided_by"] = decided_by if decided_by is not None else ""
    elif choice is not None or alternatives is not None or decided_by is not None:
        raise _error("record", "choice, alternatives, and decided_by are decision-only fields")
    # Validate the complete shape before append allocates the global ID.  The
    # temporary ID is never serialized and is replaced while holding the lock.
    if not record["id"]:
        record["id"] = {"claim": "c", "decision": "d", "question": "q"}[kind] + "1"
        validate_record(record)
        record["id"] = ""
    else:
        validate_record(record)
    return record


def validate_record(record: Any, *, previous: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Validate and return a record without mutating the caller's object.

    ``previous`` enables the ordering and cross-record relation checks used by
    both reads and appends.
    """
    if not isinstance(record, dict):
        raise _error("record", "each JSONL line must be an object")
    if any(not isinstance(key, str) for key in record):
        raise _error("record", "field names must be strings")
    if record.get("schema") in (None, 1):
        raise _error("schema", "legacy format is unsupported; migrate with scripts/migrate_ledger.py to schema 2")
    unknown_fields = sorted(set(record) - ALLOWED_FIELDS)
    if unknown_fields:
        raise _error("record", f"unknown field(s): {', '.join(unknown_fields)}")
    if type(record.get("schema")) is not int or record.get("schema") != SCHEMA:
        raise _error("schema", f"expected schema 2, got {record.get('schema')!r}")
    kind = record.get("kind")
    if kind not in KINDS:
        raise _error("record", f"kind must be one of {', '.join(KINDS)}")
    record_id = record.get("id")
    if not isinstance(record_id, str) or not ID_RE.fullmatch(record_id):
        raise _error("record", "id must match cN, dN, or qN with a positive sequence number")
    prefix, number = record_id[0], int(record_id[1:])
    expected_prefix = {"claim": "c", "decision": "d", "question": "q"}[kind]
    if prefix != expected_prefix or number < 1:
        raise _error("record", f"{kind} id {record_id!r} has the wrong prefix or sequence")
    if not isinstance(record.get("text"), str) or not record["text"].strip():
        raise _error(record_id, "text must be a non-empty string")
    state = record.get("state")
    if state not in STATES[kind]:
        raise _error(record_id, f"invalid {kind} state {state!r}")
    for field in ("ts", "author", "session", "branch", "rationale", "revisit", "cost_if_wrong"):
        if not isinstance(record.get(field), str):
            raise _error(record_id, f"{field} must be a string")
    if not isinstance(record.get("pinned"), bool):
        raise _error(record_id, "pinned must be boolean")
    if not _is_string_list(record.get("scope")):
        raise _error(record_id, "scope must be a list of non-empty strings")
    for field in ("depends_on", "answers", "supersedes"):
        if not _is_string_list(record.get(field)):
            raise _error(record_id, f"{field} must be a list of non-empty ID strings")
    supports = record.get("supports")
    if not isinstance(supports, list) or any(not _is_string_list(group) or not group for group in supports):
        raise _error(record_id, "supports must be a list of conjunctive ID lists")
    evidence = record.get("evidence")
    if not isinstance(evidence, list):
        raise _error(record_id, "evidence must be a list of objects")
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("ref"), str) or not item["ref"].strip():
            raise _error(record_id, "each evidence object needs a non-empty ref")
        for field in ("checked_at", "commit"):
            if field in item and not isinstance(item[field], str):
                raise _error(record_id, f"evidence {field} must be a string")
        if any(key not in {"ref", "checked_at", "commit"} for key in item):
            raise _error(record_id, "evidence only permits ref, checked_at, and commit")
    if kind == "decision":
        if not isinstance(record.get("choice"), str) or not record["choice"].strip():
            raise _error(record_id, "decision choice must be a non-empty string")
        if not _is_string_list(record.get("alternatives")):
            raise _error(record_id, "decision alternatives must be a list of non-empty strings")
        if record["choice"] not in record["alternatives"]:
            raise _error(record_id, "decision choice must be included in alternatives")
        if not isinstance(record.get("decided_by", ""), str):
            raise _error(record_id, "decision decided_by must be a string")
    elif "choice" in record or "alternatives" in record:
        raise _error(record_id, "choice and alternatives are decision-only fields")
    elif "decided_by" in record:
        raise _error(record_id, "decided_by is a decision-only field")
    if "legacy" in record:
        legacy = record["legacy"]
        if not isinstance(legacy, dict) or set(legacy) != {"source_id", "raw", "relation_map"}:
            raise _error(record_id, "legacy must contain source_id, raw, and relation_map")
        if not isinstance(legacy["source_id"], str) or not isinstance(legacy["raw"], dict) or not isinstance(legacy["relation_map"], dict):
            raise _error(record_id, "legacy source_id must be a string and raw/relation_map must be objects")
        if not re.fullmatch(r"d[1-9][0-9]*", legacy["source_id"]) or legacy["raw"].get("id") != legacy["source_id"]:
            raise _error(record_id, "legacy source_id must identify its raw source record")
        audit = legacy["relation_map"]
        source_fields = {"because": "supports", "depends_on": "depends_on",
                         "answers": "answers", "supersedes": "supersedes"}
        expected = {"overrides"} | {"source_" + name for name in source_fields} | {
            "mapped_" + name for name in source_fields.values()}
        if set(audit) != expected:
            raise _error(record_id, "legacy relation_map has missing or unknown audit fields")
        overrides = audit["overrides"]
        if not _is_string_list(overrides) or not set(overrides) <= set(source_fields.values()):
            raise _error(record_id, "legacy relation_map overrides must name valid relations")
        for source_name, mapped_name in source_fields.items():
            if audit["source_" + source_name] != legacy["raw"].get(source_name, []):
                raise _error(record_id, "legacy relation_map does not preserve source relations")
            if audit["mapped_" + mapped_name] != record[mapped_name]:
                raise _error(record_id, "legacy relation_map differs from the mapped relations")
    if kind == "question" and state != "open":
        raise _error(record_id, "questions have recorded state open; resolution is derived from answers")
    if kind == "question" and record["answers"]:
        raise _error(record_id, "questions cannot answer other questions")
    if kind != "decision" and record["depends_on"]:
        raise _error(record_id, "only decisions may have depends_on")

    if previous is not None:
        known = {item["id"]: item for item in previous}
        if record_id in known:
            raise _error(record_id, "duplicate ID")
        previous_numbers = [int(item["id"][1:]) for item in previous]
        if previous_numbers and number <= max(previous_numbers):
            raise _error(record_id, "global sequence must increase monotonically; gaps are allowed")
        for field in ("supports", "depends_on", "answers", "supersedes"):
            ids = [ref for group in supports for ref in group] if field == "supports" else record[field]
            for ref in ids:
                if ref == record_id:
                    raise _error(record_id, f"{field} cannot refer to itself")
                target = known.get(ref)
                if target is None:
                    raise _error(record_id, f"{field} refers to unknown or later ID {ref!r}")
                if field == "supports" and target["kind"] not in ("claim", "decision"):
                    raise _error(record_id, f"supports target {ref!r} is not a claim or decision")
                if field == "depends_on" and target["kind"] not in ("claim", "decision"):
                    raise _error(record_id, f"depends_on target {ref!r} is not a claim or decision")
                if field == "answers" and target["kind"] != "question":
                    raise _error(record_id, f"answers target {ref!r} is not a question")
                if field == "supersedes" and target["kind"] != kind:
                    raise _error(record_id, f"supersedes target {ref!r} is a different kind")
                if field == "supersedes" and ref in retired_by(previous):
                    raise _error(record_id, f"supersedes target {ref!r} is already retired")
    return copy.deepcopy(record)


def validate_entries(entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise _error("ledger", "entries must be a list")
    validated: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, 1):
        try:
            validated.append(validate_record(entry, previous=validated))
        except LedgerError as exc:
            raise _error(f"line {index}", str(exc).removeprefix("docket: ")) from exc
    return validated


# Public plural spelling is convenient for migration and import callers.
validate_records = validate_entries


def read(path: Path | str) -> list[dict[str, Any]]:
    """Read and strictly validate a ledger, raising on corruption."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise _error("read", f"cannot read {path}: {exc}") from exc
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _error(f"line {line_number}", f"invalid JSON: {exc.msg}") from exc
        try:
            entries.append(validate_record(value, previous=entries))
        except LedgerError as exc:
            raise _error(f"line {line_number}", str(exc).removeprefix("docket: ")) from exc
    return entries


def next_id(entries: list[dict[str, Any]]) -> str:
    """Allocate the next global sequence number, preserving mixed-kind IDs."""
    numbers = []
    for entry in entries:
        match = ID_RE.fullmatch(str(entry.get("id", "")))
        if match:
            numbers.append(int(match.group(2)))
    return str(max(numbers, default=0) + 1)


def allocate_id(entries: list[dict[str, Any]], kind: str) -> str:
    if kind not in KINDS:
        raise _error("record", f"unknown kind {kind!r}")
    return {"claim": "c", "decision": "d", "question": "q"}[kind] + next_id(entries)


def retired_by(entries: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in entries:
        for target in entry["supersedes"]:
            result[target] = entry["id"]
    return result


def resolved_by(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    active = {entry["id"]: entry for entry in entries}
    retired = retired_by(entries)
    applicability, _ = _decision_applicability(entries, retired)
    result: dict[str, list[str]] = {entry["id"]: [] for entry in entries}
    for entry in entries:
        if entry["kind"] not in ("claim", "decision"):
            continue
        if retired.get(entry["id"]):
            continue
        acceptable = (entry["kind"] == "claim" and entry["state"] == "accepted") or (
            entry["kind"] == "decision" and entry["state"] == "adopted" and applicability.get(entry["id"], False)
        )
        if not acceptable:
            continue
        for question_id in entry["answers"]:
            if question_id in active:
                result[question_id].append(entry["id"])
    return result


def _decision_applicability(
    entries: list[dict[str, Any]], retired: dict[str, str] | None = None,
) -> tuple[dict[str, bool], dict[str, list[str]]]:
    """Evaluate decision prerequisites without changing recorded state."""
    retired = retired if retired is not None else retired_by(entries)
    by_id = {entry["id"]: entry for entry in entries}
    applicable: dict[str, bool] = {}
    blocked: dict[str, list[str]] = {}

    def check(entry_id: str, trail: set[str]) -> tuple[bool, list[str]]:
        if entry_id in applicable:
            return applicable[entry_id], blocked[entry_id]
        entry = by_id[entry_id]
        if entry["kind"] == "claim":
            ok = entry["state"] == "accepted" and entry_id not in retired
            return ok, [] if ok else [entry_id]
        if entry["kind"] != "decision":
            return False, [entry_id]
        if entry["state"] != "adopted" or entry_id in retired:
            applicable[entry_id] = False
            blocked[entry_id] = [entry_id]
            return False, [entry_id]
        blockers: list[str] = []
        for dependency in entry["depends_on"]:
            ok, reasons = check(dependency, trail | {entry_id})
            if not ok:
                for reason in [dependency, *reasons]:
                    if reason not in blockers:
                        blockers.append(reason)
        applicable[entry_id] = not blockers
        blocked[entry_id] = blockers
        return not blockers, blockers

    for entry in entries:
        if entry["kind"] == "decision":
            check(entry["id"], set())
    return applicable, blocked


def project(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add derived retirement/resolution fields while preserving history."""
    entries = validate_entries(entries)
    retired = retired_by(entries)
    answers = resolved_by(entries)
    applicability, blocked = _decision_applicability(entries, retired)
    result = []
    for entry in entries:
        projected = copy.deepcopy(entry)
        projected["recorded_state"] = entry["state"]
        if entry["kind"] == "question" and answers[entry["id"]]:
            projected["state"] = "resolved"
        projected["retired_by"] = retired.get(entry["id"], "")
        projected["resolved_by"] = list(answers[entry["id"]])
        if entry["kind"] == "decision":
            projected["applicable"] = applicability.get(entry["id"], False)
            projected["blocked_by"] = list(blocked.get(entry["id"], []))
        result.append(projected)
    return result


def graph_payload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the graph viewer's version 2 wire representation."""
    # CLI filters may pass a projected subset whose relation targets are not
    # present in that subset.  It has already crossed the validation boundary.
    projected = copy.deepcopy(entries) if all(
        isinstance(entry, dict) and "recorded_state" in entry and "retired_by" in entry
        for entry in entries
    ) else project(entries)
    result = []
    for entry in projected:
        sets = copy.deepcopy(entry["supports"])
        union: list[str] = []
        for group in sets:
            for ref in group:
                if ref not in union:
                    union.append(ref)
        node = copy.deepcopy(entry)
        node.update({
            "question": entry["text"],
            "answer": entry.get("choice", entry.get("rationale", "")),
            "cost": entry["cost_if_wrong"],
            "sets": sets,
            "supports": union,
        })
        result.append(node)
    return {"version": 2, "entries": result}


@contextmanager
def _append_lock(path: Path) -> Iterator[None]:
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def append(path: Path | str, record: dict[str, Any]) -> dict[str, Any]:
    """Validate and append one record under a process lock.

    The caller may supply an empty id; in that case the global sequence is
    allocated while holding the lock, preventing duplicate IDs between writers.
    """
    path = Path(path)
    with _append_lock(path):
        entries = read(path)
        candidate = copy.deepcopy(record)
        if not candidate.get("id"):
            kind = candidate.get("kind")
            candidate["id"] = allocate_id(entries, kind)
        validate_record(candidate, previous=entries)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a+", encoding="utf-8") as stream:
                if stream.tell() > 0:
                    stream.seek(0, os.SEEK_END)
                    stream.seek(stream.tell() - 1)
                    if stream.read(1) != "\n":
                        stream.seek(0, os.SEEK_END)
                        stream.write("\n")
                    else:
                        stream.seek(0, os.SEEK_END)
                stream.write(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise _error("append", f"cannot write {path}: {exc}") from exc
    return candidate


def parse_evidence(value: str) -> dict[str, str]:
    """Parse a plain reference or a strict JSON evidence object."""
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {"ref": value}
    if not isinstance(decoded, dict):
        raise _error("evidence", "JSON evidence must be an object")
    return decoded
