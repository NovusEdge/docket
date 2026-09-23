"""Turning one record, or one briefing header, into text.

Split from docket.context to keep that file under the 300 line limit. Nothing
here decides what to print, only how a chosen record reads.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from docket.context_model import (
    _clip_metadata,
    _effective_state,
    _id,
    _is_retired,
    _json,
    _list,
    _recorded_state,
    _text,
)
from docket.context_select import _blocking_paths, _unavailable_reason


def _role(kind: str) -> str:
    return {
        "claim": "premise",
        "decision": "commitment",
        "question": "inquiry",
    }.get(kind.casefold(), "record")


def _index_line(entry: Mapping[str, Any], detail: int = 40) -> str:
    """One line naming a record the briefing did not render in full."""

    return " ".join(
        [
            _id(entry) or "(missing id)",
            _text(entry.get("kind") or "record").casefold(),
            _effective_state(entry),
            " " + _clip_metadata(_text(entry.get("text")), detail),
        ]
    )


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


def _footer(
    included_count: int,
    shown: int,
    deferred_count: int,
    related_count: int,
    missing_count: int,
    *,
    retired_count: int,
    no_match: bool,
) -> str:
    """The counts and the caveats that close every briefing."""

    # A retired record is never in current_ids, so it can only be counted here
    # as retired. Counting it as "in the index" would send an agent looking for
    # an index line that does not exist.
    lines = [f"# full text: {included_count}; index: {shown}; retired: {retired_count}."]
    if shown < deferred_count:
        lines.append(f"# Not listed: {deferred_count - shown}; reach them with docket list.")
    if related_count:
        lines.append(f"# Related records in index only: {related_count}; formulas remain complete.")
    # The measured set is the caller's own task matches plus their prerequisite
    # closure. The closure alone reads "covered" almost always, because a
    # blocking chain is admitted right after its root; the whole index reads
    # "partial" almost always, and an index line names a record and gives the
    # command to fetch it, so it is not a gap.
    if no_match:
        lines.append("# No task matches; the index names every current record.")
        coverage = "no matches found"
    else:
        coverage = (
            f"partial, {missing_count} in the index only"
            if missing_count
            else "task matches and their prerequisites covered"
        )
    lines.append(f"# Coverage: {coverage}. Selected ledger data only.")
    lines.append("# Declared grounds; evidence not freshly verified.")
    lines.append("# Retrieve full record: docket show RECORD_ID --json")
    return "\n\n" + "\n".join(lines) + "\n"


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
    if _list(entry.get("corrections")):
        tags.append("corrected")
    lines = [f"### {ident} | {kind} | {state} [{', '.join(tags)}]", f"role: {role}"]
    lines.append(f"text: {_text(entry.get('text'))}")
    if recorded_state != state:
        lines.append(f"recorded state: {recorded_state}")

    if kind == "decision":
        if entry.get("choice") is not None and _text(entry.get("choice")):
            lines.append(f"choice: {_text(entry.get('choice'))}")
        alternatives = [
            alternative
            for alternative in _list(entry.get("alternatives"))
            if _text(alternative) != _text(entry.get("choice"))
        ]
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
        if value and not (
            field == "rationale" and value in {_text(entry.get("text")), _text(entry.get("choice"))}
        ):
            lines.append(f"{field}: {value}")
    if _list(entry.get("evidence")):
        lines.append(f"evidence: {_json(_list(entry.get('evidence')))}")
        lines.append(
            "evidence note: references are supplied provenance and were not freshly verified by this context renderer."
        )

    provenance = []
    for field in ("author", "ts", "session", "branch"):
        value = _text(entry.get(field))
        if value:
            provenance.append(f"{field}={value}")
    if provenance:
        lines.append("provenance: " + ", ".join(provenance))
    if _is_retired(entry):
        lines.append(
            f"warning: retired by {_text(entry.get('retired_by'))}; this historical record is not current support."
        )
    unusable = (
        _is_retired(entry)
        or (kind == "claim" and state.casefold() != "accepted")
        or (
            kind == "decision"
            and (state.casefold() != "adopted" or entry.get("applicable") is False)
        )
    )
    if kind == "decision" and entry.get("applicable") is False:
        lines.append(
            "warning: decision is not applicable; treat it as unavailable current support."
        )
    elif unusable and not _is_retired(entry):
        lines.append(
            f"warning: effective state is {state}; treat this record as unavailable current support."
        )
    if _list(entry.get("resolved_by")):
        lines.append(f"resolved by: {_json(_list(entry.get('resolved_by')))}")
    if reason:
        lines.append(reason)
    return "\n".join(lines)


__all__ = ["_footer", "_header", "_index_line", "_render_record"]
