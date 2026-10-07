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
from typing import Any, NamedTuple

from docket import corrections, reviews
from docket.ledger import ID_RE, ID_TOKEN, allocate_id


class RebaseError(ValueError):
    """A tail that cannot be renumbered without producing an invalid ledger."""


_REFERENCE_FIELDS = ("depends_on", "answers", "supersedes")
PROSE_FIELDS = ("text", "choice", "alternatives", "rationale", "cost_if_wrong", "revisit")
_KIND_LETTER = {"claim": "c", "decision": "d", "question": "q"}


class ProseChange(NamedTuple):
    """One prose edit of ``renumber_per_kind``, for the ``--dry-run`` report.

    ``line_id`` is the line's id before renumbering. ``before`` and ``after``
    are the whole string, or one element of a list-valued field. An id token
    that names no mapped record is reported with ``before`` the token itself
    and ``after`` None.
    """

    line_id: str
    field: str
    before: str
    after: str | None


def rewrite_prose(
    value: Any, mapping: Mapping[str, str], via: Mapping[str, str] | None = None
) -> Any:
    """``value`` with every mapped id token replaced.

    One substitution pass with a dict lookup per token. Chaining would turn
    c3 into c1 when c3 -> c2 and c2 -> c1 are both in the mapping. ``via``
    renames a token first: a legacy line's prose cites schema-1 ids, which
    ``via`` carries to the schema-2 ids that ``mapping`` is keyed by.
    """

    def swap(match: Any) -> str:
        token = match.group(0)
        return mapping.get(via.get(token, token) if via else token, token)

    if isinstance(value, str):
        return ID_TOKEN.sub(swap, value)
    if isinstance(value, list):
        return [rewrite_prose(v, mapping, via) if isinstance(v, str) else v for v in value]
    return value


def _prose_slots(row: Mapping[str, Any]) -> list[tuple[Any, str]]:
    """The (container, key) pairs of ``row`` that hold wording."""

    kind = row.get("kind")
    if kind == corrections.KIND:
        fields = row.get("fields")
        slots: list[tuple[Any, str]] = (
            [(fields, f) for f in PROSE_FIELDS if f in fields] if isinstance(fields, dict) else []
        )
        return slots + ([(row, "reason")] if "reason" in row else [])
    if kind == reviews.KIND:
        return [(row, "note")] if "note" in row else []
    return [(row, f) for f in PROSE_FIELDS if f in row]


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


def _translated(
    record: Mapping[str, Any], mapping: Mapping[str, str], via: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """A copy of ``record`` with every ID it cites, and every id its prose mentions, mapped."""

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
    for holder, field in _prose_slots(out):
        holder[field] = rewrite_prose(holder[field], mapping, via)
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
    """The record minus its own id, ``migrated_from`` and id tokens in its prose.

    A record migrated on two branches, or merged before one of them migrated,
    carries different ids, a different ``migrated_from`` and different numbers
    in its wording on each side. Relations stay in the key, so records that
    cite different records still differ.
    """

    row = copy.deepcopy({k: v for k, v in record.items() if k not in ("id", "migrated_from")})
    for holder, field in _prose_slots(row):
        value = holder[field]
        if isinstance(value, str):
            holder[field] = ID_TOKEN.sub("#", value)
        elif isinstance(value, list):
            holder[field] = [ID_TOKEN.sub("#", v) if isinstance(v, str) else v for v in value]
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def merge(
    base: Sequence[Mapping[str, Any]],
    ours: Sequence[Mapping[str, Any]],
    theirs: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return the records of ``theirs`` to append to ``ours``, and their old-to-new IDs.

    A THEIRS record that equals an OURS record once its citations are
    translated and ids in its wording are ignored is the same recording under
    another ID, so it maps to that ID and is not appended: that is what lets a
    branch merge twice. One that
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


def _prose_changes(
    line_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    mapping: Mapping[str, str],
    via: Mapping[str, str] | None,
) -> list[ProseChange]:
    changes: list[ProseChange] = []
    for (old_holder, field), (new_holder, _) in zip(_prose_slots(before), _prose_slots(after)):
        old, new = old_holder[field], new_holder[field]
        pairs = zip(old, new) if isinstance(old, list) else [(old, new)]
        for was, now in pairs:
            if not isinstance(was, str):
                continue
            if was != now:
                changes.append(ProseChange(line_id, field, was, now))
            for match in ID_TOKEN.finditer(was):
                token = match.group(0)
                if (via.get(token, token) if via else token) not in mapping:
                    changes.append(ProseChange(line_id, field, token, None))
    return changes


def renumber_per_kind(
    records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], list[ProseChange]]:
    """Give claims, decisions and questions independent counters, in file order.

    Corrections and reviews take their target's new id and keep their suffix.
    Citations only point backwards, so the mapping built so far holds every id
    a line cites, and renumbering a prefix gives the prefix of renumbering the
    whole. A duplicate id, or a citation of an id no earlier line defines,
    raises RebaseError, because either would rewrite silently to the wrong
    record.

    A line's own id is mapped before its prose is rewritten. On a line that
    carries ``legacy.source_id``, prose tokens are schema-1 ids and resolve
    through the source ids of the lines so far first.

    Returns the new records, the old-to-new map for claims, decisions and
    questions, and every prose rewrite and unmapped token, for ``--dry-run``.
    """

    counters = {"c": 0, "d": 0, "q": 0}
    mapping: dict[str, str] = {}
    legacy_map: dict[str, str] = {}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    changes: list[ProseChange] = []
    for record in records:
        kind = record.get("kind")
        old = str(record.get("id", ""))
        if old in seen:
            raise RebaseError(f"{old} appears twice; the ledger cannot be renumbered")
        seen.add(old)
        needed = _cited(record)
        suffix: tuple[str, str, int] | None = None
        if kind in (corrections.KIND, reviews.KIND):
            module = corrections if kind == corrections.KIND else reviews
            target, number = module.parts_of(old)
            suffix = (target, "" if module is corrections else "r", number)
            needed.add(target)
        elif kind not in _KIND_LETTER:
            raise RebaseError(f"{old or 'a line'} has unknown kind {kind!r}")
        missing = sorted(n for n in needed if n not in mapping)
        if missing:
            raise RebaseError(f"{old} cites {', '.join(missing)}, which no earlier line defines")
        if kind in _KIND_LETTER:
            letter = _KIND_LETTER[kind]
            counters[letter] += 1
            mapping[old] = f"{letter}{counters[letter]}"
        legacy = record.get("legacy")
        source = legacy.get("source_id") if isinstance(legacy, dict) else None
        if isinstance(source, str):
            legacy_map[source] = old
        via = legacy_map if isinstance(source, str) else None
        row = _translated(record, mapping, via)
        if kind in _KIND_LETTER:
            row["id"] = mapping[old]
            row["migrated_from"] = old
        elif suffix is not None:
            target, mark, number = suffix
            row["id"] = f"{mapping[target]}.{mark}{number}"
        changes.extend(_prose_changes(old, record, row, mapping, via))
        out.append(row)
    return out, mapping, changes
