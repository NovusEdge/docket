"""Deterministic, character-bounded context for projected Docket history.

The context renderer deliberately knows nothing about storage or CLI path
discovery.  Its input is the projected schema 2 history produced by the ledger
module, which keeps selection and rendering easy to exercise independently.
"""

from __future__ import annotations

import fnmatch
import hashlib
import heapq
import itertools
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


try:
    # bin/docket puts lib/ on sys.path; the tests import lib.docket_context.
    from docket_config import DEFAULTS as _SETTINGS_DEFAULTS
except ImportError:
    from .docket_config import DEFAULTS as _SETTINGS_DEFAULTS


# The admission gate computes the length it once measured by rendering. Tests
# set this to check the arithmetic against the renderer on every candidate.
_VERIFY_TRIAL = False


def _list(value: Any) -> list[Any]:
    if value is None or isinstance(value, (str, bytes)):
        return []
    if isinstance(value, Sequence):
        return list(value)
    return []


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _canonical_history(entries: list[Mapping[str, Any]]) -> str:
    return json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _revision(entries: list[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256(_canonical_history(entries).encode("utf-8")).hexdigest()
    return digest[:12]


def _id(entry: Mapping[str, Any]) -> str:
    return _text(entry.get("id"))


def _is_retired(entry: Mapping[str, Any]) -> bool:
    return bool(_text(entry.get("retired_by")).strip())


def _effective_state(entry: Mapping[str, Any]) -> str:
    return _text(entry.get("state") or entry.get("recorded_state") or "unknown")


def _recorded_state(entry: Mapping[str, Any]) -> str:
    return _text(entry.get("recorded_state") or entry.get("state") or "unknown")


def _normalize_path(value: Any) -> str:
    path = _text(value).strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.casefold()


def _scope_strength(entry: Mapping[str, Any], files: tuple[str, ...],
                    weights: Mapping[str, int]) -> int:
    """Strongest scope match: exact path, then glob, then directory prefix.

    The old sort key treated every scope match as equal, so ordering between
    two matching records fell through to their position in the file.
    """

    if not files:
        return 0
    scopes = [_normalize_path(scope) for scope in _list(entry.get("scope")) if _normalize_path(scope)]
    best = 0
    for filename in files:
        path = _normalize_path(filename)
        if not path:
            continue
        for scope in scopes:
            if "/" not in scope and not any(mark in scope for mark in "*?[]"):
                continue
            if scope == path:
                best = max(best, weights["scope_exact"])
            elif fnmatch.fnmatchcase(path, scope):
                best = max(best, weights["scope_glob"])
            elif "/" in scope and path.startswith(scope.rstrip("/") + "/"):
                best = max(best, weights["scope_prefix"])
    return best




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


def _role(kind: str) -> str:
    return {
        "claim": "premise",
        "decision": "commitment",
        "question": "inquiry",
    }.get(kind.casefold(), "record")


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


def _clip_metadata(value: str, limit: int) -> str:
    value = value.replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _index_line(entry: Mapping[str, Any], detail: int = 40) -> str:
    """One line naming a record the briefing did not render in full."""

    return " ".join([
        _id(entry) or "(missing id)",
        _text(entry.get("kind") or "record").casefold(),
        _effective_state(entry),
        " " + _clip_metadata(_text(entry.get("text")), detail),
    ])


def _header(
    ledger: str,
    revision: str,
    query: str,
    files: tuple[str, ...],
    all_records: bool,
    latest: str = "",
    settings_id: str = "default",
) -> list[str]:
    identity = _clip_metadata(ledger or "ledger", 180)
    lines = [
        f"# docket: {identity} | revision: {revision}"
        + (f" | latest: {latest}" if latest else "")
        # Tuned settings change the ordering, so a briefing names the settings
        # that produced it. Without this the output is not reproducible from
        # its own header.
        + ("" if settings_id == "default" else f" | settings: {settings_id}"),
        "# Context: decisions are commitments, claims are premises, questions are inquiries; states are not truth and authors are recorders.",
    ]
    if query.strip():
        lines.append(f"# query: {_clip_metadata(query, 140)}")
    if files:
        joined = ", ".join(files)
        if len(joined) <= 180:
            lines.append(f"# files: {joined}")
        else:
            # Clipping alone loses the inputs, and the briefing must be
            # reproducible from its own header.
            digest = hashlib.sha256("\0".join(files).encode("utf-8")).hexdigest()[:8]
            lines.append(f"# files: {len(files)} paths, {digest}: {_clip_metadata(joined, 150)}")
    if all_records:
        lines.append("# selection: all current records")
    elif query.strip() or files:
        lines.append("# selection: scored by task scope and query, with related records")
    else:
        # In this mode every pinned record is already a root, so the old line
        # promising "fallback pins" described a selection that never ran.
        lines.append("# selection: scored by recency and relations; no task scope given")
    return lines


def _render_record(
    entry: Mapping[str, Any],
    relation: str,
    reason: str = "",
    by_id: Mapping[str, Mapping[str, Any]] | None = None,
    blocking_cache: dict[str, list[list[str]]] | None = None,
) -> str:
    kind = _text(entry.get("kind") or "record").casefold()
    state = _effective_state(entry)
    recorded_state = _recorded_state(entry)
    ident = _id(entry) or "(missing id)"
    role = _role(kind)
    tags = [relation]
    if bool(entry.get("pinned")):
        tags.append("pinned")
    if _is_retired(entry):
        tags.append("historical")
    lines = [f"### {ident} | {kind} | {state} [{', '.join(tags)}]", f"role: {role}"]
    lines.append(f"text: {_text(entry.get('text'))}")
    if recorded_state != state:
        lines.append(f"recorded state: {recorded_state}")

    if kind == "decision":
        if entry.get("choice") is not None and _text(entry.get("choice")):
            lines.append(f"choice: {_text(entry.get('choice'))}")
        alternatives = [alternative for alternative in _list(entry.get("alternatives"))
                        if _text(alternative) != _text(entry.get("choice"))]
        if alternatives:
            lines.append(f"alternatives: {_json(alternatives)}")
        if "applicable" in entry and entry.get("applicable") is not None:
            lines.append(f"applicable: {str(bool(entry.get('applicable'))).lower()}")
        if _list(entry.get("blocked_by")):
            lines.append(f"blocked_by: {_json(_list(entry.get('blocked_by')))}")
        if by_id:
            for path in _blocking_paths(_id(entry), by_id, cache=blocking_cache):
                terminal = by_id.get(path[-1], {})
                lines.append(f"blocked: {' -> '.join(path)} {_unavailable_reason(terminal)}")
        if _text(entry.get("decided_by")):
            lines.append(f"decided by: {_text(entry.get('decided_by'))}")
    for field in ("scope", "supports", "depends_on", "answers", "supersedes"):
        value = entry.get(field)
        if _list(value):
            lines.append(f"{field}: {_json(_list(value))}")
    for field in ("rationale", "revisit", "cost_if_wrong"):
        value = _text(entry.get(field))
        if value and not (field == "rationale" and value in {_text(entry.get("text")), _text(entry.get("choice"))}):
            lines.append(f"{field}: {value}")
    if _list(entry.get("evidence")):
        lines.append(f"evidence: {_json(_list(entry.get('evidence')))}")
        lines.append("evidence note: references are supplied provenance and were not freshly verified by this context renderer.")

    provenance = []
    for field in ("author", "ts", "session", "branch"):
        value = _text(entry.get(field))
        if value:
            provenance.append(f"{field}={value}")
    if provenance:
        lines.append("provenance: " + ", ".join(provenance))
    if _is_retired(entry):
        lines.append(f"warning: retired by {_text(entry.get('retired_by'))}; this historical record is not current support.")
    unusable = _is_retired(entry) or (
        kind == "claim" and state.casefold() != "accepted"
    ) or (
        kind == "decision" and (state.casefold() != "adopted" or entry.get("applicable") is False)
    )
    if kind == "decision" and entry.get("applicable") is False:
        lines.append("warning: decision is not applicable; treat it as unavailable current support.")
    elif unusable and not _is_retired(entry):
        lines.append(f"warning: effective state is {state}; treat this record as unavailable current support.")
    if _list(entry.get("resolved_by")):
        lines.append(f"resolved by: {_json(_list(entry.get('resolved_by')))}")
    if reason:
        lines.append(reason)
    return "\n".join(lines)


def build_delta(
    entries: Iterable[Mapping[str, Any]],
    *,
    since: str,
    baseline: Iterable[Mapping[str, Any]],
    max_chars: int | None = None,
    ledger: str = "",
    settings: Mapping[str, Any] | None = None,
) -> str | None:
    """What changed after a baseline record, or None when it is unknown.

    The ID sequence is monotonic, so a record ID fixes a point in history
    without a stored snapshot. The revision digest cannot serve here: it hashes
    the whole history, so recovery of a baseline would mean a hash of every
    prefix of the file until one matched.

    ``baseline`` is the projection as it stood at ``since``. Availability now is
    not enough to report a change: a claim recorded as disputed long before the
    baseline is unavailable and always was.
    """

    history = list(entries)
    by_id = {_id(item): item for item in history}
    since, _, expected = since.partition("@")
    if since not in by_id:
        return None
    cutoff = int(since[1:])
    prefix = [item for item in history if int(_id(item)[1:]) <= cutoff]
    if expected and _revision(prefix) != expected:
        # A rebase renumbers the tail, so this ID now covers different history.
        return None
    was_available = {_id(item) for item in baseline if _available(item)}
    cfg = settings if settings is not None else _SETTINGS_DEFAULTS
    limit = max_chars if max_chars is not None else cfg["budget"]["target"]
    added = [item for item in history if int(_id(item)[1:]) > cutoff]
    changed = [item for item in history
               if int(_id(item)[1:]) <= cutoff
               and _id(item) in was_available and not _available(item)]
    latest = max(by_id, key=lambda ident: int(ident[1:]), default="")
    revision = _revision(history)
    head = "\n".join([
        f"# docket: {_clip_metadata(ledger or 'ledger', 180)} | revision: {revision}"
        f" | latest: {latest}@{revision} | since: {since}",
        f"# changed: {len(added)} added, {len(changed)} no longer available.",
    ]) + "\n\n"
    blocks: list[str] = []
    for item in added + changed:
        block = _render_record(item, "changed", "", by_id)
        if len(head) + len("\n\n".join(blocks + [block])) > limit:
            block = _index_line(item, cfg["index"]["detail_min"])
        blocks.append(block)
    return head + "\n\n".join(blocks) + "\n"


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
    weights = cfg["weights"]
    expansion = cfg["expansion"]
    detail_min = cfg["index"]["detail_min"]
    detail_max = cfg["index"]["detail_max"]
    if max_chars is None:
        soft_limit = cfg["budget"]["target"]
        hard_limit = soft_limit * cfg["budget"]["outer_multiple"]
    else:
        if type(max_chars) is not int or max_chars < cfg["budget"]["minimum"]:
            raise ValueError(
                f"max_chars must be an integer of at least {cfg['budget']['minimum']}")
        soft_limit = hard_limit = max_chars
    history = list(entries)
    if not history:
        return ""
    query = _text(query)
    file_list = (files,) if isinstance(files, str) else tuple(files)
    by_id = {_id(item): item for item in history}
    current = [item for item in history if not _is_retired(item)]
    task_mode = not all_records and bool(query.strip() or file_list)

    order_by_id = sorted(by_id, key=lambda ident: int(ident[1:]))
    rank_of = {ident: index for index, ident in enumerate(order_by_id)}
    total_ranks = len(order_by_id)
    scores: dict[str, int] = {}
    reasons: dict[str, str] = {}
    task_matched: set[str] = set()
    term_weights = _term_weights(current, query)
    # One relation map serves scoring, adjacency, and the footer's related set,
    # so _relation_ids runs once per record for the whole briefing.
    relations = {_id(item): _relation_ids(item) for item in history}
    in_degrees: Counter[str] = Counter()
    for targets in relations.values():
        in_degrees.update(targets)

    matched = []
    for item in current:
        ident = _id(item)
        text_points = _text_points(item, query, term_weights)
        score, components = _score(
            item,
            files=file_list,
            text_points=text_points,
            degree=in_degrees[ident],
            rank=rank_of.get(ident, 0),
            total=total_ranks,
            weights=weights,
        )
        scores[ident] = score
        reasons[ident] = _selection_reason(score, components)
        # _score drops zero components, so a scope entry means a scope match.
        hit = any(name == "scope" for name, _ in components) or bool(text_points)
        if hit:
            task_matched.add(ident)
        if not task_mode or hit:
            matched.append(((-score, -int(ident[1:])), item))
    roots = [item for _, item in sorted(matched, key=lambda pair: pair[0])]
    matched_ids = {_id(item) for item in roots}
    pins = [item for item in current if item.get("pinned") and _id(item) not in matched_ids]
    no_match = task_mode and not roots
    if no_match:
        roots, pins = pins, []
    root_ids = [_id(item) for item in roots]
    selected_ids = root_ids + [_id(item) for item in pins]

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
    retired_count = sum(_is_retired(item) for item in history)
    revision = _revision(history)
    latest = max(by_id, key=lambda ident: int(ident[1:]), default="")
    if latest:
        # The digest covers the history up to and including that record, which
        # here is the whole history. A rebase renumbers the tail, so an agent
        # that passes the pair back to --since learns its baseline is stale.
        latest = f"{latest}@{revision}"
    prefix = "\n".join(
        _header(ledger, revision, query, tuple(file_list), all_records, latest, settings_id)
    ) + "\n\n"
    # Score order, so the tail trim below drops the least relevant records.
    current_ids = sorted((_id(item) for item in current),
                         key=lambda ident: (-scores.get(ident, 0), -int(ident[1:])))
    current_id_set = set(current_ids)

    # Fixed for the whole build, so the budget trial that renders a record many
    # times pays for its blocking paths once.
    blocking_cache: dict[str, list[list[str]]] = {}

    def footer_text(included_count, shown, deferred_count, related_count, missing_count):
        # A retired record is never in current_ids, so it can only be counted
        # here as retired. Counting it as "in the index" would send an agent
        # looking for an index line that does not exist.
        lines = [
            f"# full text: {included_count}; index: {shown}; retired: {retired_count}.",
        ]
        if shown < deferred_count:
            lines.append(f"# Not listed: {deferred_count - shown}; reach them with docket list.")
        if related_count:
            lines.append(f"# Related records in index only: {related_count}; formulas remain complete.")
        # The measured set is the caller's own task matches plus their
        # prerequisite closure. The closure alone reads "covered" almost always,
        # because a blocking chain is admitted right after its root; the whole
        # index reads "partial" almost always, and an index line names a record
        # and gives the command to fetch it, so it is not a gap.
        if no_match:
            lines.append("# No task matches; the index names every current record.")
            coverage = "no matches found"
        else:
            coverage = (f"partial, {missing_count} in the index only" if missing_count
                        else "task matches and their prerequisites covered")
        lines.append(f"# Coverage: {coverage}. Selected ledger data only.")
        lines.append("# Declared grounds; evidence not freshly verified.")
        lines.append("# Retrieve full record: docket show RECORD_ID --json")
        return "\n\n" + "\n".join(lines) + "\n"

    def blocking_ids(ident):
        if _text(by_id[ident].get("kind")).casefold() != "decision":
            return ()
        return [step for path in _blocking_paths(ident, by_id, cache=blocking_cache)
                for step in path]

    def footer(included, listed=None):
        deferred_count = sum(1 for ident in current_ids if ident not in included)
        shown = deferred_count if listed is None else listed
        related = {target for ident in included for target in relations[ident]
                   if target not in included and target in current_id_set}
        needed = set(task_matched)
        for ident in included:
            needed.update(blocking_ids(ident))
        return footer_text(len(included), shown, deferred_count, len(related),
                           len(needed - included))

    # Shorten only diagnostic metadata. Propositions and relationship formulas
    # are never sliced, even when the caller supplies a giant path or query.
    if len(prefix) + len(footer(set())) > hard_limit:
        prefix = f"# docket: {_clip_metadata(ledger or 'ledger', 60)} | revision: {revision}\n\n"
    included: set[str] = set()
    order: list[str] = []
    labels: dict[str, str] = {}
    top_score = max(scores.values(), default=0) or 1

    def detail_of(ident):
        span = detail_max - detail_min
        return detail_min + (scores.get(ident, 0) * span) // top_score

    record_cache: dict[tuple[str, str], str] = {}

    def rendered_record(ident):
        key = (ident, labels[ident])
        if key not in record_cache:
            record_cache[key] = _render_record(
                by_id[ident], labels[ident], reasons.get(ident, ""), by_id,
                blocking_cache=blocking_cache)
        return record_cache[key]

    def render(candidate_order, candidate_set, index_ids=None, detail=None, names_only=False):
        full = "\n\n".join(rendered_record(i) for i in candidate_order)
        pool = current_ids if index_ids is None else index_ids
        deferred = [i for i in pool if i not in candidate_set]
        # Score order, so the cap keeps the records closest to the task.
        shown = deferred[:cfg["index"]["max_lines"]]
        parts = [prefix.rstrip("\n"), ""]
        if full:
            parts += [full, ""]
        if shown:
            if names_only:
                parts.append("# index: " + ", ".join(shown))
            else:
                parts.append(f"# index: {len(shown)} more current records")
                parts.append("\n".join(
                    _index_line(by_id[i], detail_of(i) if detail is None else detail)
                    for i in shown
                ))
            if len(deferred) > len(shown):
                parts.append(f"# and {len(deferred) - len(shown)} more; docket list")
        return "\n".join(parts).rstrip("\n") + footer(candidate_set, len(shown))

    # Counters for the admission trial. Rendering the whole briefing to measure
    # each candidate cost O(n) per admit, so a 10000-record ledger took 20s.
    body_length = 0
    deferred_count = len(current_ids)
    related_pending: set[str] = set()
    needed_ids = set(task_matched)
    missing_count = len(needed_ids)
    base_length = len(prefix.rstrip("\n"))
    index_head = len("# index: ")
    max_lines = cfg["index"]["max_lines"]

    # The index names at most max_lines records, so the gate prices a sliding
    # window over current_ids instead of the whole list. The cursor only moves
    # forward, which keeps the whole admission pass linear.
    window: list[str] = []
    window_length = 0
    cursor = 0

    def _fill_window():
        nonlocal cursor, window_length
        while len(window) < max_lines and cursor < len(current_ids):
            candidate = current_ids[cursor]
            cursor += 1
            if candidate not in included:
                window.append(candidate)
                window_length += len(candidate)

    def _next_after_window(exclude):
        """The name that would enter the window if one left it."""

        scan = cursor
        while scan < len(current_ids):
            candidate = current_ids[scan]
            if candidate not in included and candidate != exclude:
                return candidate
            scan += 1
        return ""

    _fill_window()

    def _trial_length(ident):
        """Length of the briefing that admitting ident would produce.

        This mirrors render(order + [ident], included | {ident}, names_only=True)
        exactly. A rendered record is never empty, so the full-text block is
        always present and only the index part varies.
        """

        full = body_length + len(rendered_record(ident)) + 2 * len(order)
        deferred = deferred_count - (1 if ident in current_id_set else 0)
        length, shown = window_length, len(window)
        if ident in window:
            length -= len(ident)
            shown -= 1
            entering = _next_after_window(ident)
            if entering:
                length += len(entering)
                shown += 1
        if shown:
            index = index_head + length + 2 * (shown - 1)
            total = base_length + full + index + 4
            if deferred > shown:
                total += len(f"# and {deferred - shown} more; docket list") + 1
        else:
            # "\n".join ends with the empty part, and rstrip drops that newline.
            total = base_length + full + 2
        # Counted by difference. Copying either set per candidate was itself
        # O(n), which left a 100000-record briefing at 135s.
        related = len(related_pending) - (1 if ident in related_pending else 0)
        added: set[str] = set()
        for target in relations[ident]:
            if (target != ident and target not in included and target not in related_pending
                    and target in current_id_set and target not in added):
                added.add(target)
                related += 1
        missing = missing_count - (1 if ident in needed_ids else 0)
        added.clear()
        for step in blocking_ids(ident):
            if step not in needed_ids and step not in included and step not in added:
                added.add(step)
                missing += 1
        return total + len(footer_text(len(included) + 1, shown, deferred,
                                       related, missing))

    def admit(ident, label, mandatory=False):
        nonlocal body_length, deferred_count, window_length, missing_count
        if ident in included:
            return True
        labels[ident] = label
        # A task match may push past the target. Nothing may push past the
        # ceiling, which equals the target whenever the caller named one.
        limit = hard_limit if mandatory else soft_limit
        if _VERIFY_TRIAL:
            measured = len(render(order + [ident], included | {ident}, names_only=True))
            computed = _trial_length(ident)
            if measured != computed:
                raise AssertionError(
                    f"trial length for {ident}: computed {computed}, rendered {measured}")
        if _trial_length(ident) > limit:
            del labels[ident]
            # A refused candidate never reaches the output, so its rendered text
            # is dead. Keeping every one cost 35 MB at 40000 records.
            record_cache.pop((ident, label), None)
            return False
        included.add(ident)
        order.append(ident)
        body_length += len(rendered_record(ident))
        if ident in current_id_set:
            deferred_count -= 1
        if ident in window:
            window.remove(ident)
            window_length -= len(ident)
            _fill_window()
        related_pending.discard(ident)
        related_pending.update(target for target in relations[ident]
                               if target not in included and target in current_id_set)
        if ident in needed_ids:
            missing_count -= 1
        for step in blocking_ids(ident):
            if step not in needed_ids:
                needed_ids.add(step)
                if step not in included:
                    missing_count += 1
        return True

    def _largest_fitting_keep(head, chosen_order, chosen_set, deferred_ids):
        """How many bare names fit, over the same descending sequence as before.

        Length rises with the name count, so the sequence splits into a refused
        prefix and an accepted suffix. Probing it by bisection costs a handful
        of length computations instead of one render per step.
        """

        if not deferred_ids:
            return 0
        steps = []
        count = len(deferred_ids)
        while count > 0:
            steps.append(count)
            count -= max(1, count // 8)
        sums = [0, *itertools.accumulate(len(ident) for ident in deferred_ids)]
        body = sum(len(rendered_record(i)) for i in chosen_order)
        full = body + 2 * (len(chosen_order) - 1) if chosen_order else 0
        related = {target for ident in chosen_set for target in relations[ident]
                   if target not in chosen_set and target in current_id_set}
        needed = set(task_matched)
        for ident in chosen_set:
            needed.update(blocking_ids(ident))
        missing = len(needed - chosen_set)
        base = len(head.rstrip("\n")) + (full + 4 if chosen_order else 2)

        def length(keep):
            # render names at most max_lines of them and then says how many it
            # left out, so trimming past the cap only changes that count.
            shown = min(keep, max_lines)
            index = index_head + sums[shown] + 2 * (shown - 1)
            if keep > shown:
                index += len(f"# and {keep - shown} more; docket list") + 1
            tail = footer_text(len(chosen_set), shown, len(deferred_ids),
                               len(related), missing)
            computed = base + index + len(tail)
            if _VERIFY_TRIAL:
                measured = len(render(chosen_order, chosen_set, deferred_ids[:keep],
                                      names_only=True))
                if measured != computed:
                    raise AssertionError(
                        f"trim length at keep={keep}: computed {computed}, rendered {measured}")
            return computed

        # Naming every record drops the "Not listed" line, so length falls at
        # the top of the range. Test the whole set first, then bisect the rest,
        # where length does rise with the name count.
        if length(steps[0]) <= hard_limit:
            return steps[0]
        low, high = 1, len(steps)
        while low < high:
            middle = (low + high) // 2
            if length(steps[middle]) <= hard_limit:
                high = middle
            else:
                low = middle + 1
        if low == len(steps):
            return 0
        return steps[low]

    for ident in root_ids:
        admit(ident, "selected", mandatory=ident in task_matched)

    # A blocked decision's explanation inherits the decision's own budget
    # standing, ahead of the frontier: a neighbour that scores higher would
    # otherwise take the slot and leave the decision unexplained.
    for ident in root_ids:
        if ident not in included:
            continue
        for path in _blocking_paths(ident, by_id, cache=blocking_cache):
            for step in path:
                admit(step, "blocking prerequisite", mandatory=ident in task_matched)

    def expand(seeds):
        # Adjacency order is an artefact of insertion, so a flat cap on it
        # discarded neighbours by accident. Walk by inherited score instead.
        frontier = [(-scores.get(i, 0), -int(i[1:]), i, scores.get(i, 0))
                    for i in seeds if i in included]
        heapq.heapify(frontier)
        seen = set(included)
        while frontier:
            _, _, ident, parent_score = heapq.heappop(frontier)
            decayed = (parent_score * expansion["decay_numerator"]
                       // expansion["decay_denominator"])
            if decayed < expansion["floor"]:
                continue
            ranked = sorted(
                (t for t in adjacency[ident] if t not in seen),
                key=lambda t: (-(decayed if t not in scores else min(scores[t], decayed)),
                               -int(t[1:])),
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
                if admit(target, "related record"):
                    heapq.heappush(frontier,
                                   (-effective, -int(target[1:]), target, effective))

    expand(root_ids)
    for item in pins:
        ident = _id(item)
        if admit(ident, "fallback pin"):
            expand([ident])
    result = render(order, included)
    if len(result) > hard_limit:
        # Degrade in order: shrink every index line to the minimum detail, then
        # drop to bare IDs, then trim the ID list. Bare IDs come before any
        # trimming because they cost a few characters each, so naming thirty
        # records that way is cheaper than listing four in full.
        flat = render(order, included, detail=detail_min)
        if len(flat) <= hard_limit:
            return flat
        # Trim the deferred list, not current_ids: records already in the
        # full-text tier occupy the head of current_ids, so trimming that list
        # would drop index lines while appearing to keep them.
        # Keep the full-text tier if it fits alongside bare names; drop it only
        # when even that overruns, and report the tier counts either way.
        short = f"# docket: {_clip_metadata(ledger or 'ledger', 60)} | revision: {revision}\n\n"
        for head in (prefix, short):
            prefix = head
            for chosen_order, chosen_set in ((order, included), ([], set())):
                deferred_ids = [i for i in current_ids if i not in chosen_set]
                keep = _largest_fitting_keep(head, chosen_order, chosen_set, deferred_ids)
                if keep:
                    return render(chosen_order, chosen_set, deferred_ids[:keep],
                                  names_only=True)
        result = (f"# docket revision: {revision}\n# No records fit.\n"
                  "# Retrieve full record: docket show RECORD_ID --json\n")
    return result


__all__ = ["build_context", "build_delta"]
