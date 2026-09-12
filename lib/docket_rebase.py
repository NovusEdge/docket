"""Renumber a divergent ledger tail onto this one.

Two branches that both record decisions allocate the same IDs, so a git merge
of an append-only ledger produces either a conflict or a file that fails to
read. Renumbering resolves it: the tail after the common prefix takes fresh
IDs, and references inside that tail follow. References into the prefix stay
valid, because prefix IDs never move, and no prefix record can reference the
tail because validation forbids forward references.

Every function here takes raw read() output. project() adds derived fields
that depend on the whole history, so two diverged branches disagree on those
fields for their shared records and the common prefix would measure zero.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

try:
    # bin/docket puts lib/ on sys.path; the tests import lib.docket_rebase.
    from docket_ledger import ID_RE, allocate_id
except ImportError:
    from .docket_ledger import ID_RE, allocate_id


class RebaseError(ValueError):
    """A tail that cannot be renumbered without producing an invalid ledger."""


_REFERENCE_FIELDS = ("depends_on", "answers", "supersedes")

# A migrated record carries legacy.relation_map, whose mapped_* fields
# validation requires to equal the record's own relations
# (lib/docket_ledger.py:236-237). Rewriting the relations without the audit map
# makes append reject the record. Every record in a migrated ledger carries
# this, so a rebase that skipped it would fail on the first tail record.
_AUDIT_FIELDS = {
    "supports": "mapped_supports",
    "depends_on": "mapped_depends_on",
    "answers": "mapped_answers",
    "supersedes": "mapped_supersedes",
}


def common_prefix(mine: Sequence[Mapping[str, Any]],
                  theirs: Sequence[Mapping[str, Any]]) -> int:
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


def renumber(mine: Sequence[Mapping[str, Any]],
             theirs: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return their tail with fresh IDs, and the old-to-new ID map."""

    shared = common_prefix(mine, theirs)
    tail = [copy.deepcopy(record) for record in theirs[shared:]]
    if not tail:
        return [], {}

    already_retired = _retired_in(mine)
    for record in tail:
        for target in record.get("supersedes") or ():
            if str(target) in already_retired:
                raise RebaseError(
                    f"both histories supersede {target}; resolve that by hand "
                    "before rebasing")

    allocated = [dict(record) for record in mine]
    mapping: dict[str, str] = {}
    for record in tail:
        old = str(record.get("id", ""))
        if not ID_RE.fullmatch(old):
            raise RebaseError(f"malformed id {old!r} in the incoming tail")
        new = allocate_id(allocated, str(record.get("kind")))
        mapping[old] = new
        record["id"] = new
        allocated.append(record)

    for record in tail:
        for field in _REFERENCE_FIELDS:
            values = record.get(field)
            if values:
                record[field] = [mapping.get(str(v), str(v)) for v in values]
        groups = record.get("supports")
        if groups:
            record["supports"] = [[mapping.get(str(v), str(v)) for v in group]
                                  for group in groups]
        _rewrite_audit(record)
    return tail, mapping


def _rewrite_audit(record: dict[str, Any]) -> None:
    """Keep a migrated record's relation_map equal to its rewritten relations.

    source_* fields keep the original pre-migration IDs untouched: they record
    what the schema 1 ledger said, which renumbering does not change.
    """

    audit = (record.get("legacy") or {}).get("relation_map")
    if not isinstance(audit, Mapping):
        return
    updated = dict(audit)
    for field, mapped in _AUDIT_FIELDS.items():
        if mapped in updated:
            updated[mapped] = copy.deepcopy(record.get(field))
    record["legacy"] = {**record["legacy"], "relation_map": updated}
