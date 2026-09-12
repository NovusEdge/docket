"""Deterministic, character-bounded context for projected Docket history.

The context renderer deliberately knows nothing about storage or CLI path
discovery.  Its input is the projected schema 2 history produced by the ledger
module, which keeps selection and rendering easy to exercise independently.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


try:
    # bin/docket puts lib/ on sys.path; the tests import lib.docket_context.
    from docket_config import DEFAULTS as _SETTINGS_DEFAULTS
except ImportError:
    from .docket_config import DEFAULTS as _SETTINGS_DEFAULTS

_DEFAULT_BUDGET = _SETTINGS_DEFAULTS["budget"]["target"]
_MINIMUM_BUDGET = _SETTINGS_DEFAULTS["budget"]["minimum"]


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


def _scope_matches(entry: Mapping[str, Any], files: tuple[str, ...]) -> bool:
    """Match normalized repo-relative paths against path scopes.

    Scopes containing a slash or glob metacharacter use ``fnmatch`` and
    literal path scopes also match descendants. Bare component scopes are
    intentionally query-only and never match a ``--file`` value.
    """

    if not files:
        return False
    scopes = [_normalize_path(scope) for scope in _list(entry.get("scope")) if _normalize_path(scope)]
    if not scopes:
        return False
    for filename in files:
        path = _normalize_path(filename)
        if not path:
            continue
        for scope in scopes:
            if "/" not in scope and not any(mark in scope for mark in "*?[]"):
                continue
            if fnmatch.fnmatchcase(path, scope):
                return True
            if "/" in scope and path.startswith(scope.rstrip("/") + "/"):
                return True
    return False


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


def _degree(ident: str, history: list[Mapping[str, Any]]) -> int:
    return sum(ident in _relation_ids(item) for item in history)


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
        weight = 1000 * (total - frequency) // total
        # A term in every record scores zero and is dropped. Keeping it at 1
        # would make every record a task match, so one common word in the
        # query would select the whole ledger.
        if frequency and weight:
            weights[term] = weight
    return weights


def _text_points(entry: Mapping[str, Any], query: str, weights: Mapping[str, int]) -> int:
    if not weights:
        return 0
    haystack = _haystack(entry)
    points = sum(weight for term, weight in weights.items() if term in haystack)
    if query.strip().casefold() in haystack:
        points += 1000
    return points


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
        lines.append(f"# files: {_clip_metadata(', '.join(files), 180)}")
    if all_records:
        lines.append("# selection: all current records")
    elif query.strip() or files:
        lines.append("# selection: scored by task scope and query, with related records")
    else:
        # In this mode every pinned record is already a root, so the old line
        # promising "fallback pins" described a selection that never ran.
        lines.append("# selection: scored by recency and relations; no task scope given")
    return lines


def _render_record(entry: Mapping[str, Any], relation: str, reason: str = "") -> str:
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

    matched = []
    for item in current:
        ident = _id(item)
        text_points = _text_points(item, query, term_weights)
        score, components = _score(
            item,
            files=file_list,
            text_points=text_points,
            degree=_degree(ident, history),
            rank=rank_of.get(ident, 0),
            total=total_ranks,
            weights=weights,
        )
        scores[ident] = score
        reasons[ident] = _selection_reason(score, components)
        hit = bool(_scope_strength(item, file_list, weights) or text_points)
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

    adjacency = {ident: [] for ident in by_id}
    for item in history:
        ident = _id(item)
        for target in _relation_ids(item):
            if target not in by_id:
                continue
            if target not in adjacency[ident]:
                adjacency[ident].append(target)
            if ident not in adjacency[target]:
                adjacency[target].append(ident)
    candidate_ids = set(selected_ids)
    for ident in selected_ids:
        candidate_ids.update(adjacency[ident])
    retired_count = sum(_is_retired(item) and _id(item) not in candidate_ids for item in history)
    revision = _revision(history)
    latest = max(by_id, key=lambda ident: int(ident[1:]), default="")
    prefix = "\n".join(
        _header(ledger, revision, query, tuple(file_list), all_records, latest, settings_id)
    ) + "\n\n"
    # Score order, so the tail trim below drops the least relevant records.
    current_ids = sorted((_id(item) for item in current),
                         key=lambda ident: (-scores.get(ident, 0), -int(ident[1:])))

    def footer(included, listed=None):
        deferred = [ident for ident in current_ids if ident not in included]
        shown = len(deferred) if listed is None else listed
        related_omitted = {target for ident in included for target in _relation_ids(by_id[ident])
                           if target not in included}
        lines = [
            f"# full text: {len(included)}; index: {shown}; retired: {retired_count}.",
        ]
        if shown < len(deferred):
            lines.append(f"# Not listed: {len(deferred) - shown}; the budget could not name them.")
        if related_omitted:
            lines.append(f"# Related records in index only: {len(related_omitted)}; formulas remain complete.")
        if no_match:
            lines.append("# No task matches; the index names every current record.")
        lines.append("# Declared grounds; evidence not freshly verified.")
        lines.append("# Retrieve full record: docket show RECORD_ID --json")
        return "\n\n" + "\n".join(lines) + "\n"

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

    def render(candidate_order, candidate_set, index_ids=None, detail=None):
        full = "\n\n".join(
            _render_record(by_id[i], labels[i], reasons.get(i, "")) for i in candidate_order
        )
        pool = current_ids if index_ids is None else index_ids
        deferred = [i for i in pool if i not in candidate_set]
        parts = [prefix.rstrip("\n"), ""]
        if full:
            parts += [full, ""]
        if deferred:
            parts.append(f"# index: {len(deferred)} more current records")
            parts.append("\n".join(
                _index_line(by_id[i], detail_of(i) if detail is None else detail)
                for i in deferred
            ))
        return "\n".join(parts).rstrip("\n") + footer(candidate_set, len(deferred))

    def admit(ident, label, mandatory=False):
        if ident in included:
            return True
        labels[ident] = label
        # A task match may push past the target. Nothing may push past the
        # ceiling, which equals the target whenever the caller named one.
        limit = hard_limit if mandatory else soft_limit
        if len(render(order + [ident], included | {ident})) > limit:
            del labels[ident]
            return False
        included.add(ident)
        order.append(ident)
        return True

    for ident in root_ids:
        admit(ident, "selected", mandatory=ident in task_matched)

    def expand(seeds):
        # Adjacency order is an artefact of insertion, so a flat cap on it
        # discarded neighbours by accident. Walk by inherited score instead.
        frontier = [(-scores.get(i, 0), -int(i[1:]), i, scores.get(i, 0))
                    for i in seeds if i in included]
        seen = set(included)
        while frontier:
            frontier.sort()
            _, _, ident, parent_score = frontier.pop(0)
            decayed = (parent_score * expansion["decay_numerator"]
                       // expansion["decay_denominator"])
            if decayed < expansion["floor"]:
                continue
            ranked = sorted(
                (t for t in adjacency[ident] if t not in seen),
                key=lambda t: (-min(scores.get(t, 0), decayed), -int(t[1:])),
            )
            for target in ranked:
                seen.add(target)
                effective = min(scores.get(target, 0), decayed) or decayed
                if effective < expansion["floor"]:
                    continue
                if admit(target, "related record"):
                    frontier.append((-effective, -int(target[1:]), target, effective))

    expand(root_ids)
    for item in pins:
        ident = _id(item)
        if admit(ident, "fallback pin"):
            expand([ident])
    result = render(order, included)
    if len(result) > hard_limit:
        # Degrade in order: shrink every index line to the minimum detail, then
        # trim index lines from the low-scoring tail, then names alone.
        flat = render(order, included, detail=detail_min)
        if len(flat) <= hard_limit:
            return flat
        keep = len(current_ids)
        while keep > 0:
            keep -= max(1, keep // 8)
            candidate = render(order, included, current_ids[:keep], detail=detail_min)
            if len(candidate) <= hard_limit:
                return candidate
        # No index line fits. Name the records by ID alone, which costs a few
        # characters each and keeps every current record recoverable. The
        # diagnostic prefix goes first when even that does not fit.
        ids = ", ".join(i for i in current_ids if i not in included)
        short = f"# docket: {_clip_metadata(ledger or 'ledger', 60)} | revision: {revision}"
        for head in (prefix.rstrip("\n"), short):
            candidate = head + f"\n\n# index: {ids}" + footer(included, 0)
            if len(candidate) <= hard_limit:
                return candidate
        result = (f"# docket revision: {revision}\n# No records fit.\n"
                  "# Retrieve full record: docket show RECORD_ID --json\n")
    return result


__all__ = ["build_context"]
