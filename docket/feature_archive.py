"""Move closed, unreferenced feature events into a dated file.

Split out of docket.features to keep that file under the 300 line limit.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from docket.features import read
from docket.ledger import ledger_lock


def archive(store: Path, archive_dir: Path, *, keep: set[str]) -> tuple[int, Path | None]:
    """Move every event of a feature not named in ``keep`` into a dated file.

    d96 sets the mechanism for the ledger and features follow it: a record
    count never triggers the move, and nothing moves while something still
    references it. The destination is named by the digest of the events that
    moved, so two archives from two branches never collide on a filename.
    """

    events = read(store)
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

    with ledger_lock(store):
        with target.open("a", encoding="utf-8") as stream:
            for event in moving:
                stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        with store.open("w", encoding="utf-8") as stream:
            for event in staying:
                stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return len(moving), target


__all__ = ["archive"]
