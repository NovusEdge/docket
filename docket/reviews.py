"""Review lines: a reader's acknowledgment that a flagged record still stands.

A review pins each ground the record itself owes, to the head it resolved to
when reviewed. The flag clears only while that head is still the head, so a
later revision of the same chain raises it again. A flag inherited from a
flagged or blocked ground is never pinned; it clears when that ground does.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from docket.support import INHERITED

KIND = "review"
REVIEW_RE = re.compile(r"([cdq](?:0|[1-9][0-9]*))\.r([1-9][0-9]*)")
_LINE_FIELDS = frozenset(
    {"schema", "kind", "id", "reviews", "grounds", "note", "ts", "author", "session", "branch"}
)


def split_id(ident: str) -> tuple[str, int] | None:
    match = REVIEW_RE.fullmatch(ident)
    return (match.group(1), int(match.group(2))) if match else None


def parts_of(ident: str) -> tuple[str, int]:
    parts = split_id(ident)
    if parts is None:
        raise ValueError(f"not a review id: {ident!r}")
    return parts


def validate(record: dict[str, Any], prefix: Any) -> dict[str, Any]:
    """Validate a review line; ``prefix`` is a ledger._Prefix or None."""
    from docket.ledger import SCHEMA, _error

    ident = record.get("id")
    if not isinstance(ident, str) or (parts := split_id(ident)) is None:
        raise _error("record", "review id must match <record id>.r<n> with n from 1")
    unknown = sorted(set(record) - _LINE_FIELDS)
    if unknown:
        raise _error(ident, f"unknown field(s): {', '.join(unknown)}")
    if type(record.get("schema")) is not int or record["schema"] != SCHEMA:
        raise _error("schema", f"expected schema {SCHEMA}, got {record.get('schema')!r}")
    for field in ("ts", "author", "session", "branch", "note"):
        if not isinstance(record.get(field), str):
            raise _error(ident, f"{field} must be a string")
    target_id, number = parts
    if record.get("reviews") != target_id:
        raise _error(ident, "a review id must start with the id it reviews")
    grounds = record.get("grounds")
    if (
        not isinstance(grounds, dict)
        or not grounds
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in grounds.items())
    ):
        raise _error(ident, "grounds must be a non-empty object of ground id to head id")
    if prefix is None:
        return copy.deepcopy(record)
    target = prefix.by_id.get(target_id)
    if target is None or target["kind"] not in ("claim", "decision"):
        raise _error(ident, f"reviews unknown, later, or non-claim/decision ID {target_id!r}")
    for ground, head in grounds.items():
        for ref in (ground, head):
            if ref not in prefix.by_id:
                raise _error(ident, f"grounds refer to unknown or later ID {ref!r}")
    if number <= prefix.reviews.get(target_id, 0):
        raise _error(ident, "review numbers must increase for each record; gaps are allowed")
    return copy.deepcopy(record)


def fold(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Records with their review lines attached as ``reviews``, the lines removed."""
    result: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for entry in entries:
        if entry.get("kind") != KIND:
            index[entry["id"]] = len(result)
            result.append(entry)
            continue
        position = index[entry["reviews"]]
        current = dict(result[position])
        current["reviews"] = [
            *current.get("reviews", []),
            {"id": entry["id"], "grounds": dict(entry["grounds"]), "note": entry["note"]},
        ]
        result[position] = current
    return result


def allocate(entries: list[dict[str, Any]], target: str) -> str:
    highest = 0
    for entry in entries:
        if entry.get("kind") == KIND and entry.get("reviews") == target:
            highest = max(highest, parts_of(entry["id"])[1])
    return f"{target}.r{highest + 1}"


def make(
    target: str,
    *,
    note: str = "",
    author: str = "unknown",
    session: str = "",
    branch: str = "",
    ts: str | None = None,
) -> dict[str, Any]:
    """An unnumbered review line; append allocates the id and fills grounds under its lock."""
    from datetime import datetime, timezone

    from docket.ledger import SCHEMA

    return {
        "schema": SCHEMA,
        "kind": KIND,
        "id": "",
        "reviews": target,
        "grounds": {},
        "note": note,
        "ts": ts if ts is not None else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "author": author,
        "session": session,
        "branch": branch,
    }


def refuse(entries: list[dict[str, Any]], review: dict[str, Any]) -> None:
    """Fill ``grounds`` with what the record owes now, or refuse a review of nothing."""
    from docket.ledger import _error, project

    target = next(
        (e for e in project(entries, validated=True) if e["id"] == review["reviews"]), None
    )
    if target is None or target["kind"] not in ("claim", "decision"):
        raise _error(review["id"], f"no claim or decision {review['reviews']!r} to review")
    owed = target.get("review_owed") or []
    if not owed:
        raise _error(review["id"], "nothing to review: the record owes no review")
    own = [item for item in owed if item["because"] not in INHERITED]
    if not own:
        grounds = ", ".join(dict.fromkeys(item["ground"] for item in owed))
        raise _error(
            review["id"],
            f"nothing to review on {review['reviews']}: its flags come from {grounds}; "
            "review or fix those",
        )
    review["grounds"] = {item["ground"]: item["head"] for item in own}
