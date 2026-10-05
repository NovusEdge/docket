"""Renumber a divergent ledger tail onto this one.

Two branches that both record decisions allocate the same IDs, so a git merge
of an append-only ledger produces either a conflict or a file that fails to
read. Renumbering resolves it: each record after the common prefix is matched
against our tail, and one with no counterpart takes a fresh ID. References
inside the appended records follow. References into the prefix stay valid,
because prefix IDs never move, and no prefix record can reference the tail
because validation forbids forward references.

Every function here takes raw read() output. project() adds derived fields
that depend on the whole history, so two diverged branches disagree on those
fields for their shared records and the common prefix would measure zero.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from typing import Any

from docket import corrections, reviews
from docket.ledger import ID_RE, allocate_id


class RebaseError(ValueError):
    """A tail that cannot be renumbered without producing an invalid ledger."""


_REFERENCE_FIELDS = ("depends_on", "answers", "supersedes")


def common_prefix(mine: Sequence[Mapping[str, Any]], theirs: Sequence[Mapping[str, Any]]) -> int:
    """How many leading records the two histories share exactly."""

    count = 0
    for left, right in zip(mine, theirs):
        if left != right:
            break
        count += 1
    return count


def _retired_in(records: Sequence[Mapping[str, Any]]) -> set[str]:
    retired = set()
    for record in records:
        for target in record.get("supersedes") or ():
            retired.add(str(target))
    return retired


def _translated(record: Mapping[str, Any], mapping: Mapping[str, str]) -> dict[str, Any]:
    """A copy of ``record`` with every ID it cites passed through ``mapping``."""

    def get(value: Any) -> str:
        return mapping.get(str(value), str(value))

    out = copy.deepcopy(dict(record))
    if out.get("kind") == corrections.KIND:
        out["corrects"] = get(out.get("corrects"))
    elif out.get("kind") == reviews.KIND:
        out["reviews"] = get(out.get("reviews"))
        out["grounds"] = {get(g): get(h) for g, h in (out.get("grounds") or {}).items()}
    for field in _REFERENCE_FIELDS:
        if out.get(field):
            out[field] = [get(v) for v in out[field]]
    if out.get("supports"):
        out["supports"] = [[get(v) for v in group] for group in out["supports"]]
    return out


def _cited(record: Mapping[str, Any]) -> set[str]:
    cited = {str(v) for field in _REFERENCE_FIELDS for v in record.get(field) or ()}
    cited |= {str(v) for group in record.get("supports") or () for v in group}
    for field in ("corrects", "reviews"):
        if record.get(field):
            cited.add(str(record[field]))
    for ground, head in (record.get("grounds") or {}).items():
        cited |= {str(ground), str(head)}
    return cited


def _key(record: Mapping[str, Any]) -> str:
    """The record minus its own id, so a renumbered copy compares equal."""

    return json.dumps(
        {k: v for k, v in record.items() if k != "id"}, sort_keys=True, ensure_ascii=False
    )


def merge(
    base: Sequence[Mapping[str, Any]],
    ours: Sequence[Mapping[str, Any]],
    theirs: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return the records of ``theirs`` to append to ``ours``, and their old-to-new IDs.

    A THEIRS record that equals an OURS record once its citations are
    translated is the same recording under another ID, so it maps to that ID
    and is not appended: that is what lets a branch merge twice. One that
    equals a BASE record but no OURS record was removed or rewritten on our
    side and stays out, which keeps a cherry-pick from importing the picked
    commit's whole history. Citations only point backwards, so one pass in
    file order has every citation's mapping in hand.
    """

    shared = common_prefix(ours, theirs)
    mapping: dict[str, str] = {}
    waiting: dict[str, list[str]] = {}
    for record in ours[shared:]:
        waiting.setdefault(_key(record), []).append(str(record["id"]))
    in_base = {_key(record) for record in base}
    already_retired = _retired_in(ours)
    allocated: list[dict[str, Any]] = [dict(record) for record in ours]
    dropped: set[str] = set()
    tail: list[dict[str, Any]] = []
    moved: dict[str, str] = {}

    for record in theirs[shared:]:
        old = str(record.get("id", ""))
        candidate = _translated(record, mapping)
        matches = waiting.get(_key(candidate))
        if matches:
            mapping[old] = matches.pop(0)
            continue
        if _key(record) in in_base:
            dropped.add(old)
            continue
        missing = sorted(_cited(record) & dropped)
        if missing:
            raise RebaseError(
                f"{old} cites {', '.join(missing)}, which this side does not have; merge by hand"
            )
        for target in candidate.get("supersedes") or ():
            if str(target) in already_retired:
                raise RebaseError(
                    f"both histories supersede {target}; resolve that by hand before rebasing"
                )
        if candidate.get("kind") == corrections.KIND:
            # Counted against allocated, which holds ours and the tail so far,
            # so two incoming corrections of one record take distinct numbers.
            new = corrections.allocate(allocated, str(candidate["corrects"]))
        elif candidate.get("kind") == reviews.KIND:
            new = reviews.allocate(allocated, str(candidate["reviews"]))
        else:
            if not ID_RE.fullmatch(old):
                raise RebaseError(f"malformed id {old!r} in the incoming tail")
            new = allocate_id(allocated, str(candidate.get("kind")))
        candidate["id"] = new
        mapping[old] = new
        moved[old] = new
        allocated.append(candidate)
        tail.append(candidate)
    return tail, moved


def renumber(
    mine: Sequence[Mapping[str, Any]], theirs: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return their tail with fresh IDs, and the old-to-new ID map."""

    return merge([], mine, theirs)
