"""Field-level corrections to earlier ledger records.

A correction line names one earlier record and replaces some of its wording
and metadata. The record keeps its id, so every relation, feature include,
and citation that names it still does. Supersession stays the way to change
what a record commits to, which is why choice, state, and relations are fixed.
"""

from __future__ import annotations

import copy
import re
from typing import Any

KIND = "correction"
CORRECTION_RE = re.compile(r"([cdq](?:0|[1-9][0-9]*))\.([1-9][0-9]*)")
_COMMON = frozenset(
    {"text", "rationale", "scope", "cost_if_wrong", "evidence", "revisit", "pinned"}
)
_DECISION_ONLY = frozenset({"alternatives", "decided_by"})
_LINE_FIELDS = frozenset(
    {"schema", "kind", "id", "corrects", "fields", "reason", "ts", "author", "session", "branch"}
)


def split_id(ident: str) -> tuple[str, int] | None:
    match = CORRECTION_RE.fullmatch(ident)
    return (match.group(1), int(match.group(2))) if match else None


def parts_of(ident: str) -> tuple[str, int]:
    """split_id for an id that validation already accepted."""
    parts = split_id(ident)
    if parts is None:
        raise ValueError(f"not a correction id: {ident!r}")
    return parts


def correctable(kind: str) -> frozenset[str]:
    return _COMMON | _DECISION_ONLY if kind == "decision" else _COMMON


def validate(record: dict[str, Any], prefix: Any) -> dict[str, Any]:
    """Validate a correction line; ``prefix`` is a ledger._Prefix or None.

    Without a prefix only the line's own shape is checked, as validate_record
    does for a record.
    """
    from docket.ledger import SCHEMA, _error, validate_record

    ident = record.get("id")
    if not isinstance(ident, str) or (parts := split_id(ident)) is None:
        raise _error("record", "correction id must match <record id>.<n> with n from 1")
    unknown = sorted(set(record) - _LINE_FIELDS)
    if unknown:
        raise _error(ident, f"unknown field(s): {', '.join(unknown)}")
    if type(record.get("schema")) is not int or record["schema"] != SCHEMA:
        raise _error("schema", f"expected schema {SCHEMA}, got {record.get('schema')!r}")
    for field in ("ts", "author", "session", "branch", "reason"):
        if not isinstance(record.get(field), str):
            raise _error(ident, f"{field} must be a string")
    target_id, number = parts
    if record.get("corrects") != target_id:
        raise _error(ident, "a correction id must start with the id it corrects")
    fields = record.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise _error(ident, "fields must be a non-empty object")
    if prefix is None:
        return copy.deepcopy(record)
    target = prefix.by_id.get(target_id)
    if target is None:
        raise _error(ident, f"corrects unknown or later ID {target_id!r}")
    fixed = sorted(set(fields) - _COMMON - _DECISION_ONLY)
    if fixed:
        raise _error(
            ident,
            f"cannot correct {', '.join(fixed)} on a {target['kind']}; "
            "supersede the record to change it",
        )
    if target["kind"] != "decision":
        decision_only = sorted(set(fields) & _DECISION_ONLY)
        if decision_only:
            noun = "field" if len(decision_only) == 1 else "fields"
            raise _error(ident, f"{', '.join(decision_only)} is a decision-only {noun}")
    if number <= prefix.corrections.get(target_id, 0):
        raise _error(ident, "correction numbers must increase for each record; gaps are allowed")
    # The record's own type rules check each replacement value.
    validate_record({**target, **copy.deepcopy(fields)})
    return copy.deepcopy(record)


def fold(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Records with their corrections applied, the correction lines removed.

    ``original`` holds each corrected field's value before its first
    correction. A record with no corrections is passed through untouched, so
    its revision digest does not change.
    """
    result: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for entry in entries:
        if entry.get("kind") != KIND:
            index[entry["id"]] = len(result)
            result.append(entry)
            continue
        position = index[entry["corrects"]]
        current = dict(result[position])
        original = dict(current.get("original", {}))
        for field, value in entry["fields"].items():
            original.setdefault(field, copy.deepcopy(current.get(field)))
            current[field] = copy.deepcopy(value)
        current["original"] = original
        current["corrections"] = [*current.get("corrections", []), entry["id"]]
        result[position] = current
    return result


def allocate(entries: list[dict[str, Any]], target: str) -> str:
    highest = 0
    for entry in entries:
        if entry.get("kind") == KIND and entry.get("corrects") == target:
            highest = max(highest, parts_of(entry["id"])[1])
    return f"{target}.{highest + 1}"


def make(
    target: str,
    fields: dict[str, Any],
    *,
    reason: str = "",
    author: str = "unknown",
    session: str = "",
    branch: str = "",
    ts: str | None = None,
) -> dict[str, Any]:
    """An unnumbered correction line; append allocates the id under its lock."""
    from datetime import datetime, timezone

    from docket.ledger import SCHEMA

    return {
        "schema": SCHEMA,
        "kind": KIND,
        "id": "",
        "corrects": target,
        "fields": copy.deepcopy(fields),
        "reason": reason,
        "ts": ts if ts is not None else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "author": author,
        "session": session,
        "branch": branch,
    }


def refuse(entries: list[dict[str, Any]], correction: dict[str, Any]) -> None:
    """Drop no-op fields and run the write-time refusals on what remains.

    A field whose replacement value equals the record's current projected
    value changes nothing, so it is dropped before the echo and question-text
    refusals run and before the reduced fields are written. A correction left
    with no field is itself refused: it would append a line that changes
    nothing the reader can see.

    Only the fields the correction still carries are checked, against the
    record as earlier corrections left it.
    """
    from docket.ledger import _error, _reject_empty_reasoning, _reject_question_text

    target = next(item for item in fold(entries) if item["id"] == correction["corrects"])
    reduced = {
        field: value for field, value in correction["fields"].items() if target.get(field) != value
    }
    if not reduced:
        raise _error(correction["id"], "nothing to correct: every field already has that value")
    correction["fields"] = reduced
    record = {**target, **reduced}
    if "text" in reduced:
        _reject_question_text(record)
    if record["kind"] == "decision":
        _reject_empty_reasoning(record, frozenset(reduced))
