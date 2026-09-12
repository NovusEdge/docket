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


_DEFAULT_BUDGET = 8000
_MINIMUM_BUDGET = 512


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


def _text_matches(entry: Mapping[str, Any], query: str) -> bool:
    query = query.strip().casefold()
    if not query:
        return False
    fields = [
        entry.get("id"),
        entry.get("text"),
        entry.get("rationale"),
        entry.get("choice"),
        *_list(entry.get("alternatives")),
        *_list(entry.get("scope")),
    ]
    haystack = " ".join(_text(value) for value in fields).casefold()
    if query in haystack:
        return True
    words = [word for word in query.split() if word]
    return bool(words) and all(word in haystack for word in words)


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


def _header(
    ledger: str,
    revision: str,
    query: str,
    files: tuple[str, ...],
    all_records: bool,
) -> list[str]:
    identity = _clip_metadata(ledger or "ledger", 180)
    lines = [
        f"# docket: {identity} | revision: {revision}",
        "# Context: decisions are commitments, claims are premises, questions are inquiries; states are not truth and authors are recorders.",
    ]
    if query.strip():
        lines.append(f"# query: {_clip_metadata(query, 140)}")
    if files:
        lines.append(f"# files: {_clip_metadata(', '.join(files), 180)}")
    if all_records:
        lines.append("# selection: all current records")
    else:
        lines.append("# selection: pinned, matching, and directly related records")
    return lines


def _render_record(entry: Mapping[str, Any], relation: str) -> str:
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
    return "\n".join(lines)


def build_context(
    entries: Iterable[Mapping[str, Any]],
    *,
    query: str = "",
    files: Iterable[str] = (),
    max_chars: int = _DEFAULT_BUDGET,
    ledger: str = "",
    all_records: bool = False,
) -> str:
    """Render whole records within a strict character budget.

    Task roots have priority over neighbors and fallback pins. Related records
    are admitted only after their root fits. Traversal is one hop in either
    direction, with at most 64 related records admitted.
    """
    if type(max_chars) is not int or max_chars < _MINIMUM_BUDGET:
        raise ValueError("max_chars must be an integer of at least 512")
    history = list(entries)
    if not history:
        return ""
    query = _text(query)
    file_list = (files,) if isinstance(files, str) else tuple(files)
    by_id = {_id(item): item for item in history}
    current = [item for item in history if not _is_retired(item)]
    task_mode = not all_records and bool(query.strip() or file_list)

    matched = []
    for index, item in enumerate(current):
        scope = int(_scope_matches(item, file_list))
        text = int(_text_matches(item, query))
        if not task_mode or scope or text:
            matched.append(((-scope, -text, -int(bool(item.get("pinned"))), index), item))
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
    unrelated_count = len(history) - len(candidate_ids) - retired_count
    revision = _revision(history)
    prefix = "\n".join(_header(ledger, revision, query, tuple(file_list), all_records)) + "\n\n"

    def omitted_id_text(ids):
        chosen = []
        for ident in ids:
            if len(chosen) >= 8 or len(", ".join(chosen + [ident])) > 120:
                break
            chosen.append(ident)
        return ", ".join(chosen) + (f" (+{len(ids) - len(chosen)} more)" if len(chosen) < len(ids) else "")

    def footer(included):
        omitted_roots = [ident for ident in selected_ids if ident not in included]
        related_omitted = {target for ident in included for target in _relation_ids(by_id[ident])
                           if target not in included}
        lines = [
            f"# Omitted: {len(candidate_ids - included)}; unrelated: {unrelated_count}; retired: {retired_count}.",
        ]
        if omitted_roots:
            lines.append("# Omitted selected IDs: " + omitted_id_text(omitted_roots))
        pinned_missing = sum(bool(by_id[ident].get("pinned")) for ident in omitted_roots)
        if pinned_missing:
            lines.append(f"# Omitted pinned records: {pinned_missing}.")
        if related_omitted:
            lines.append(f"# Related records omitted: {len(related_omitted)}; formulas remain complete.")
        if no_match:
            lines.append("# No task matches; fallback pins and their related records may be shown.")
        lines.append("# Declared grounds; evidence not freshly verified.")
        lines.append("# Retrieve full record: docket show RECORD_ID --json")
        return "\n\n" + "\n".join(lines) + "\n"

    # Shorten only diagnostic metadata. Propositions and relationship formulas
    # are never sliced, even when the caller supplies a giant path or query.
    if len(prefix) + len(footer(set())) > max_chars:
        prefix = f"# docket: {_clip_metadata(ledger or 'ledger', 60)} | revision: {revision}\n\n"
    included = set()
    blocks = []

    def admit(ident, label):
        if ident in included:
            return True
        block = _render_record(by_id[ident], label)
        trial = included | {ident}
        rendered = prefix + "\n\n".join([*blocks, block]) + footer(trial)
        if len(rendered) > max_chars:
            return False
        included.add(ident)
        blocks.append(block)
        return True

    for ident in root_ids:
        admit(ident, "selected")
    related_admitted = 0

    def neighbors(ident):
        nonlocal related_admitted
        if ident not in included:
            return
        for target in adjacency[ident]:
            # A selected root that did not fit cannot reappear as a neighbor.
            if target in selected_ids or target in included:
                continue
            if related_admitted >= 64:
                break
            if admit(target, "related record"):
                related_admitted += 1

    for ident in root_ids:
        neighbors(ident)
    for item in pins:
        ident = _id(item)
        if admit(ident, "fallback pin"):
            neighbors(ident)
    result = prefix + "\n\n".join(blocks) + footer(included)
    if len(result) > max_chars:
        # This can only be diagnostic overhead with no admitted record.
        result = (f"# docket revision: {revision}\n# No complete records fit.\n"
                  f"# Omitted selected IDs: {omitted_id_text(selected_ids)}\n"
                  "# Retrieve full record: docket show RECORD_ID --json\n")
    return result


__all__ = ["build_context"]
