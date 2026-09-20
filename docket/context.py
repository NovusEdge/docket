"""Deterministic, character-bounded context for projected Docket history.

The context renderer deliberately knows nothing about storage or CLI path
discovery.  Its input is the projected schema 2 history produced by the ledger
module, which keeps selection and rendering easy to exercise independently.

The work splits by responsibility, each part in its own module: context_model
reads a record's fields, context_select scores and relates records,
context_render turns one into text, context_budget decides how many fit,
context_degrade handles a result that still overruns, and context_delta
answers a resumed session. This file is the order those run in.
"""

from __future__ import annotations

import heapq
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from docket.config import DEFAULTS as _SETTINGS_DEFAULTS
from docket.context_budget import Admission
from docket.context_degrade import degrade
from docket.context_delta import build_delta
from docket.context_model import (
    _clip_metadata,
    _id,
    _is_retired,
    _revision,
    _text,
    positions,
    scope_strength,
)
from docket.context_render import _header
from docket.context_select import _blocking_paths, _relation_ids, rank_records

# The admission gate computes the length it once measured by rendering. Tests
# set this to check the arithmetic against the renderer on every candidate.
_VERIFY_TRIAL = False


def _feature_prefix(feature: str, limit: int) -> str:
    """The feature brief, clipped at a line boundary, or an empty string.

    A quarter of this call's own budget, the same share the spec fixes for the
    brief inside docket context. It sits above even the ledger's own header
    line, because that header cites the latest record id and would otherwise
    put a record ahead of the feature naming the work in progress.

    The block goes into `prefix`, and every budget test downstream measures
    `prefix`. Subtracting its length from the limits as well charged it twice,
    so a briefing lost about two characters of records for every character of
    header.
    """

    if not feature:
        return ""
    clipped: list[str] = []
    used = 0
    truncated = False
    for line in feature.splitlines():
        added = len(line) + 1
        if used + added > limit and clipped:
            truncated = True
            break
        clipped.append(line)
        used += added
    block = "\n".join(clipped)
    if truncated:
        block += "\n# feature brief truncated to fit the budget"
    return block + "\n\n"


def build_context(
    entries: Iterable[Mapping[str, Any]],
    *,
    query: str = "",
    files: Iterable[str] = (),
    max_chars: int | None = None,
    ledger: str = "",
    all_records: bool = False,
    settings: Mapping[str, Any] | None = None,
    settings_id: str = "default",
    feature: str = "",
) -> str:
    """Render whole records under tiered budget rules.

    Every current record appears, in full text or as an index line. A record
    that matches the task scope or query renders in full even when that
    exceeds the default target, up to budget.outer_multiple times the target.
    Everything else competes for the remaining target by score.

    A caller that names ``max_chars`` gets a hard ceiling instead, and no rule
    may exceed it.
    """
    cfg = settings if settings is not None else _SETTINGS_DEFAULTS
    expansion = cfg["expansion"]
    if max_chars is None:
        soft_limit = cfg["budget"]["target"]
        hard_limit = soft_limit * cfg["budget"]["outer_multiple"]
    else:
        if type(max_chars) is not int or max_chars < cfg["budget"]["minimum"]:
            raise ValueError(f"max_chars must be an integer of at least {cfg['budget']['minimum']}")
        soft_limit = hard_limit = max_chars
    history = list(entries)
    if not history:
        return ""
    query = _text(query)
    file_list = (files,) if isinstance(files, str) else tuple(files)
    by_id = {_id(item): item for item in history}
    current = [item for item in history if not _is_retired(item)]
    task_mode = not all_records and bool(query.strip() or file_list)

    at = positions(history)
    rank_of = at
    # One relation map serves scoring, adjacency, and the footer's related set,
    # so _relation_ids runs once per record for the whole briefing.
    relations = {_id(item): _relation_ids(item) for item in history}
    in_degrees: Counter[str] = Counter()
    for targets in relations.values():
        in_degrees.update(targets)

    scores, reasons, task_matched = rank_records(
        current,
        query=query,
        files=file_list,
        weights=cfg["weights"],
        rank_of=rank_of,
        total_ranks=len(at),
        in_degrees=in_degrees,
    )
    matched = [
        ((-scores[_id(item)], -at[_id(item)]), item)
        for item in current
        if not task_mode or _id(item) in task_matched
    ]
    roots = [item for _, item in sorted(matched, key=lambda pair: pair[0])]
    matched_ids = {_id(item) for item in roots}
    pins = [item for item in current if item.get("pinned") and _id(item) not in matched_ids]
    no_match = task_mode and not roots
    if no_match:
        roots, pins = pins, []
    root_ids = [_id(item) for item in roots]

    # expand() sorts each neighbour list by inherited score, so insertion order
    # carries nothing. A set keeps the reverse edges unique without scanning.
    adjacency: dict[str, set[str]] = {ident: set() for ident in by_id}
    for item in history:
        ident = _id(item)
        for target in relations[ident]:
            if target not in by_id:
                continue
            adjacency[ident].add(target)
            adjacency[target].add(ident)
    revision = _revision(history)
    latest = max(by_id, key=lambda ident: at[ident], default="")
    if latest:
        # The digest covers the history up to and including that record, which
        # here is the whole history. A rebase renumbers the tail, so an agent
        # that passes the pair back to --since learns its baseline is stale.
        latest = f"{latest}@{revision}"
    feature_prefix = _feature_prefix(feature, max(1, soft_limit // 4))
    prefix = (
        feature_prefix
        + "\n".join(
            _header(ledger, revision, query, tuple(file_list), all_records, latest, settings_id)
        )
        + "\n\n"
    )
    short = f"# docket: {_clip_metadata(ledger or 'ledger', 60)} | revision: {revision}\n\n"
    # Score order, so the tail trim below drops the least relevant records.
    current_ids = sorted(
        (_id(item) for item in current), key=lambda ident: (-scores.get(ident, 0), -at[ident])
    )
    # Fixed for the whole build, so the budget trial that renders a record many
    # times pays for its blocking paths once.
    blocking_cache: dict[str, list[list[str]]] = {}

    budget = Admission(
        by_id=by_id,
        current_ids=current_ids,
        relations=relations,
        scores=scores,
        reasons=reasons,
        task_matched=task_matched,
        prefix=prefix,
        cfg=cfg,
        soft_limit=soft_limit,
        hard_limit=hard_limit,
        retired_count=sum(_is_retired(item) for item in history),
        no_match=no_match,
        blocking_cache=blocking_cache,
        verify=_VERIFY_TRIAL,
    )
    budget.shrink_prefix(feature_prefix + short)

    for ident in root_ids:
        budget.admit(ident, "selected", mandatory=ident in task_matched)

    # A blocked decision's explanation inherits the decision's own budget
    # standing, ahead of the frontier: a neighbour that scores higher would
    # otherwise take the slot and leave the decision unexplained.
    for ident in root_ids:
        if ident not in budget.included:
            continue
        for path in _blocking_paths(ident, by_id, cache=blocking_cache):
            for step in path:
                budget.admit(step, "blocking prerequisite", mandatory=ident in task_matched)

    def expand(seeds):
        # Adjacency order is an artefact of insertion, so a flat cap on it
        # discarded neighbours by accident. Walk by inherited score instead.
        frontier = [
            (-scores.get(i, 0), -at[i], i, scores.get(i, 0)) for i in seeds if i in budget.included
        ]
        heapq.heapify(frontier)
        seen = set(budget.included)
        while frontier:
            _, _, ident, parent_score = heapq.heappop(frontier)
            decayed = parent_score * expansion["decay_numerator"] // expansion["decay_denominator"]
            if decayed < expansion["floor"]:
                continue
            ranked = sorted(
                (t for t in adjacency[ident] if t not in seen),
                key=lambda t: (
                    -(decayed if t not in scores else min(scores[t], decayed)),
                    -at[t],
                ),
            )
            for target in ranked:
                seen.add(target)
                # A retired record carries no score, because scoring runs over
                # current records only. It inherits the parent's decayed score
                # so a cited historical premise can still be reached. A current
                # record that scored zero keeps its zero and is dropped.
                effective = decayed if target not in scores else min(scores[target], decayed)
                if effective < expansion["floor"]:
                    continue
                if budget.admit(target, "related record"):
                    heapq.heappush(frontier, (-effective, -at[target], target, effective))

    expand(root_ids)
    for item in pins:
        ident = _id(item)
        if budget.admit(ident, "fallback pin"):
            expand([ident])
    result = budget.render(budget.order, budget.included)
    if len(result) <= hard_limit:
        return result
    return degrade(budget, current_ids=current_ids, short=short, revision=revision)


__all__ = ["build_context", "build_delta", "scope_strength"]
