"""What changed since a baseline record.

Split from docket.context to keep that file under the 300 line limit. A delta
answers a resumed session, so it has no budget tiers and no selection: every
changed record appears, in full text or as one index line.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from docket.config import DEFAULTS as _SETTINGS_DEFAULTS
from docket.context_model import _clip_metadata, _id, _revision
from docket.context_render import _index_line, _render_record
from docket.context_select import _available


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
    changed = [
        item
        for item in history
        if int(_id(item)[1:]) <= cutoff and _id(item) in was_available and not _available(item)
    ]
    latest = max(by_id, key=lambda ident: int(ident[1:]), default="")
    revision = _revision(history)
    head = (
        "\n".join(
            [
                f"# docket: {_clip_metadata(ledger or 'ledger', 180)} | revision: {revision}"
                f" | latest: {latest}@{revision} | since: {since}",
                f"# changed: {len(added)} added, {len(changed)} no longer available.",
            ]
        )
        + "\n\n"
    )
    blocks: list[str] = []
    for item in added + changed:
        block = _render_record(item, "changed", "", by_id)
        if len(head) + len("\n\n".join(blocks + [block])) > limit:
            block = _index_line(item, cfg["index"]["detail_min"])
        blocks.append(block)
    return head + "\n\n".join(blocks) + "\n"


__all__ = ["build_delta"]
