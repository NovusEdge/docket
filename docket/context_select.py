"""Which records a briefing selects, and why.

Split from docket.context to keep that file under the 300 line limit. Nothing
here renders anything: a function returns a score, a relation, or a reason.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from docket.context_model import (
    _effective_state,
    _id,
    _is_retired,
    _list,
    _scope_strength,
    _text,
)


def _score(
    entry: Mapping[str, Any],
    *,
    files: tuple[str, ...],
    text_points: int,
    degree: int,
    rank: int,
    total: int,
    weights: Mapping[str, int],
) -> tuple[int, list[tuple[str, int]]]:
    """Return an integer score and the components that produced it."""

    components = [
        ("scope", _scope_strength(entry, files, weights)),
        ("text", weights["text"] * min(text_points, 1000) // 1000),
        ("recency", weights["recency"] * rank // max(1, total - 1)),
        ("degree", weights["degree"] * min(degree, weights["degree_cap"])),
        ("pinned", weights["pinned"] if entry.get("pinned") else 0),
    ]
    return sum(value for _, value in components), [pair for pair in components if pair[1]]


def _selection_reason(score: int, components: list[tuple[str, int]]) -> str:
    detail = ", ".join(f"{name}={value}" for name, value in components)
    return f"selection: score {score} | {detail}"


def _haystack(entry: Mapping[str, Any]) -> str:
    fields = [
        entry.get("id"),
        entry.get("text"),
        entry.get("rationale"),
        entry.get("choice"),
        *_list(entry.get("alternatives")),
        *_list(entry.get("scope")),
    ]
    return " ".join(_text(value) for value in fields).casefold()


def _term_weights(current: list[Mapping[str, Any]], query: str) -> dict[str, int]:
    """Weight each query term by how few records contain it.

    Integer division, not a logarithm: libm results can differ between
    platforms, and a briefing must be byte-identical at one revision.
    """

    terms = [word for word in query.strip().casefold().split() if word]
    if not terms or not current:
        return {}
    haystacks = [_haystack(item) for item in current]
    total = len(haystacks)
    weights = {}
    for term in terms:
        frequency = sum(term in haystack for haystack in haystacks)
        # Smoothed by one record. Without it a term present in every record
        # scores zero, so a focused query against a focused ledger matches
        # nothing: three records all about postgres and the query "postgres"
        # selected none of them. The smoothing keeps a universal term worth
        # 250 points on a three-record ledger and 3 points on a three-hundred
        # record one, which is the discrimination the weight is there to
        # express.
        if frequency:
            weights[term] = 1000 * (total + 1 - frequency) // (total + 1)
    return weights


def _text_points(entry: Mapping[str, Any], query: str, weights: Mapping[str, int]) -> int:
    query = query.strip().casefold()
    if not query:
        return 0
    haystack = _haystack(entry)
    # The phrase bonus is checked before the term weights, because it earns its
    # keep exactly when every term is common and the weights are all small.
    points = 1000 if query in haystack else 0
    return points + sum(weight for term, weight in weights.items() if term in haystack)


def _relation_ids(entry: Mapping[str, Any]) -> list[str]:
    """Return direct relation targets in a stable, de-duplicated order."""

    result: list[str] = []
    seen: set[str] = set()
    for group in _list(entry.get("supports")):
        for target in _list(group):
            target_id = _text(target)
            if target_id and target_id not in seen:
                seen.add(target_id)
                result.append(target_id)
    for field in ("depends_on", "answers", "resolved_by"):
        for target in _list(entry.get(field)):
            target_id = _text(target)
            if target_id and target_id not in seen:
                seen.add(target_id)
                result.append(target_id)
    return result


def _available(entry: Mapping[str, Any]) -> bool:
    """True when a record can serve as current support."""

    if _is_retired(entry):
        return False
    kind = _text(entry.get("kind")).casefold()
    state = _effective_state(entry).casefold()
    if kind == "claim":
        return state == "accepted"
    if kind == "decision":
        return state == "adopted" and entry.get("applicable") is not False
    return False


def _unavailable_reason(entry: Mapping[str, Any]) -> str:
    """Why a record cannot serve as current support.

    The effective state does not say this. A retired claim still reads
    "accepted", and a blocked decision still reads "adopted", so printing the
    state on a blocking path would name the chain and then contradict it.
    """

    if _is_retired(entry):
        return "retired"
    if _text(entry.get("kind")).casefold() == "decision" and entry.get("applicable") is False:
        return "blocked"
    return _effective_state(entry)


def _blocking_paths(
    ident: str,
    by_id: Mapping[str, Mapping[str, Any]],
    depth: int = 8,
    cache: dict[str, list[list[str]]] | None = None,
) -> list[list[str]]:
    """Each path of prerequisites from a decision to an unavailable record.

    The projection flattens prerequisites: `_decision_applicability` collects
    `[dependency, *reasons]` into one list, so `blocked_by` cannot tell a
    two-step chain from two direct prerequisites.

    The result is fixed for the whole build, so ``cache`` lets one briefing
    share it across the budget trial that renders a record many times.
    """

    # The cache key omits depth, so a caller that changes it must not share one.
    if cache is not None and depth != 8:
        raise ValueError("_blocking_paths cache assumes the default depth")
    if cache is not None and ident in cache:
        return cache[ident]

    paths: list[list[str]] = []

    def walk(current: str, trail: tuple[str, ...]) -> None:
        if len(trail) > depth:
            return
        entry = by_id.get(current)
        if entry is None:
            return
        for target in _list(entry.get("depends_on")):
            target_id = _text(target)
            if not target_id or target_id in trail or target_id not in by_id:
                continue
            if _available(by_id[target_id]):
                continue
            step = trail + (target_id,)
            before = len(paths)
            walk(target_id, step)
            if len(paths) == before:
                paths.append(list(step[1:]))

    walk(ident, (ident,))
    if cache is not None:
        cache[ident] = paths
    return paths


def rank_records(
    current: list[Mapping[str, Any]],
    *,
    query: str,
    files: tuple[str, ...],
    weights: Mapping[str, int],
    rank_of: Mapping[str, int],
    total_ranks: int,
    in_degrees: Mapping[str, int],
) -> tuple[dict[str, int], dict[str, str], set[str]]:
    """Score every current record: the scores, the printed reasons, the hits.

    A hit is a record the caller's own task named, through scope or through
    text. It decides which records may exceed the soft budget, so it is
    returned rather than recomputed from the scores, where a scope component
    of zero is indistinguishable from no scope at all.
    """

    scores: dict[str, int] = {}
    reasons: dict[str, str] = {}
    hits: set[str] = set()
    term_weights = _term_weights(current, query)
    for item in current:
        ident = _id(item)
        text_points = _text_points(item, query, term_weights)
        score, components = _score(
            item,
            files=files,
            text_points=text_points,
            degree=in_degrees.get(ident, 0),
            rank=rank_of.get(ident, 0),
            total=total_ranks,
            weights=weights,
        )
        scores[ident] = score
        reasons[ident] = _selection_reason(score, components)
        # _score drops zero components, so a scope entry means a scope match.
        if any(name == "scope" for name, _ in components) or text_points:
            hits.add(ident)
    return scores, reasons, hits


__all__ = [
    "_available",
    "_blocking_paths",
    "_relation_ids",
    "_term_weights",
    "_unavailable_reason",
    "rank_records",
]
