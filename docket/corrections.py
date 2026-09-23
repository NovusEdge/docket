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


def correctable(kind: str) -> frozenset[str]:
    return _COMMON | _DECISION_ONLY if kind == "decision" else _COMMON


def validate(record: dict[str, Any], prefix: Any) -> dict[str, Any]:
    """Validate a correction line; ``prefix`` is a ledger._Prefix or None.

    Without a prefix only the line's own shape is checked, as validate_record
    does for a record.
    """
    from docket.ledger import SCHEMA, _error, validate_record

    ident = record.get("id")
    parts = split_id(ident) if isinstance(ident, str) else None
    if parts is None:
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
    refused = sorted(set(fields) - correctable(target["kind"]))
    if refused:
        raise _error(
            ident,
            f"cannot correct {', '.join(refused)} on a {target['kind']}; "
            "supersede the record to change it",
        )
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
