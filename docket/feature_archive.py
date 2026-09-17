"""Move closed feature events into a dated file.

Split out of docket.features to keep that file under the 300 line limit.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from docket.features import ID_RE, read
from docket.ledger import ledger_lock


def archive_dir_for(store: Path) -> Path:
    return store.parent / "archive"


def archived_events(store: Path) -> list[dict[str, Any]]:
    """Every event in every archive file beside this store."""

    directory = archive_dir_for(store)
    if not directory.is_dir():
        return []
    events: list[dict[str, Any]] = []
    for name in sorted(directory.glob("features-*.jsonl")):
        events.extend(read(name))
    return events


def highest_archived_id(store: Path) -> int:
    """The largest f-number the archive holds.

    An id is a permanent address, so `gc` must not free one for reuse. next_id
    reads the live store alone, and after an archive that store no longer
    carries the moved ids, so a new feature would take f1 again and every
    citation to the archived f1 would silently retarget.
    """

    highest = 0
    for event in archived_events(store):
        match = ID_RE.fullmatch(str(event.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def _write_lines(target: Path, events: list[dict[str, Any]]) -> None:
    """Replace ``target`` with these events through a temporary file.

    A truncate in place loses every remaining event when the process dies or
    the disk fills partway through, and those events are not in the archive
    yet either.
    """

    staging = target.with_name(target.name + ".tmp")
    with staging.open("w", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, target)


def archive(store: Path, archive_dir: Path, *, keep: set[str]) -> tuple[int, Path | None]:
    """Move every event of a feature not named in ``keep`` into a dated file.

    d96 sets the mechanism for the ledger and features follow it: a record
    count never triggers the move. The destination is named by the digest of
    the events that moved, so two archives from two branches never collide on
    a filename.

    Everything runs under the store's own lock, including the read. Reading
    first and locking afterwards let a concurrent append land in the window,
    and the rewrite then destroyed it.
    """

    with ledger_lock(store):
        events = read(store, lock=False)
        if not events:
            return 0, None
        moving = [event for event in events if event["slug"] not in keep]
        if not moving:
            return 0, None
        staying = [event for event in events if event["slug"] in keep]

        canonical = "\n".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for event in moving
        )
        revision = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        archive_dir.mkdir(parents=True, exist_ok=True)
        target = archive_dir / f"features-{revision}.jsonl"

        # The digest names the events, so re-archiving the same set would
        # append them twice and make the archive unreadable.
        existing = {str(event["id"]) for event in read(target)} if target.exists() else set()
        fresh = [event for event in moving if str(event["id"]) not in existing]
        if fresh:
            with target.open("a", encoding="utf-8") as stream:
                for event in fresh:
                    stream.write(
                        json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
                    )
                stream.flush()
                os.fsync(stream.fileno())
        _write_lines(store, staying)
    return len(moving), target


__all__ = ["archive", "archive_dir_for", "archived_events", "highest_archived_id"]
