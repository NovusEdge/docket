"""Store maintenance for the feature command group: remap and gc.

Split from docket.cli.feature to keep that file under the 300 line limit.
These two verbs maintain the store itself. Every other verb records or reads
one feature.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from docket import env, feature_archive, feature_project, features


def archived(path: Path) -> list[dict[str, Any]]:
    """Every projected feature in every archive file beside the live store."""

    return feature_project.project(feature_archive.archived_events(path))


def closed_at(path: Path, feature_id: str) -> str:
    """When this feature's own run closed, or the empty string.

    A slug is reusable after a close, so several runs share one slug and the
    events interleave with other slugs' events. Tracking the open run per slug
    is the only way to attribute a close event to the run that started it.
    """

    open_run: dict[str, str] = {}
    for event in features.read(path):
        slug, verb = event["slug"], event["event"]
        if verb == "start":
            open_run[slug] = event["id"]
        elif verb in ("done", "abandon"):
            if open_run.get(slug) == feature_id:
                return event["ts"]
            open_run.pop(slug, None)
    return ""


def cmd_feature_remap(args) -> int:
    """Repoint include and exclude lists through a rebase's id map.

    Append-only: every correction is a new amend event. Rewriting the original
    start or amend line in place is what hooks/guard_ledger.py exists to stop.
    """

    from docket.cli.feature import record_event

    source = Path(args.mapfile)
    try:
        mapping = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"docket: {source}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(mapping, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()
    ):
        print(f"docket: {source}: expected a JSON object of old id to new id", file=sys.stderr)
        return 1

    path = env.features_path()
    # Read the raw events, never the projection. A union merge is the reason
    # this command exists, and project() refuses a store holding two events
    # with one id. Projecting first made remap die with the error that names
    # remap as the fix.
    events = features.read(path)
    duplicates = feature_project.duplicate_ids(events)
    if duplicates:
        print(
            "docket: cannot repoint a store with duplicate ids: "
            + ", ".join(f"{ident} ({', '.join(slugs)})" for ident, slugs in duplicates),
            file=sys.stderr,
        )
        print(
            "docket: renumber them by hand first; two branches recorded the same id",
            file=sys.stderr,
        )
        return 1

    changes = feature_project.remap_changes(feature_project.project(events), mapping)
    for slug, fields in changes:
        features.append(path, record_event("amend", slug, **fields))
    print(f"docket: remapped {len(changes)} feature(s)")
    return 0


def cmd_feature_gc(args) -> int:
    path = env.features_path()
    current = feature_project.project(features.read(path))
    keep = set()
    cutoff = ""
    if args.expire:
        moment = datetime.now(timezone.utc) - timedelta(days=args.expire)
        cutoff = moment.isoformat(timespec="seconds")
    for feature in current:
        if feature["state"] not in features.TERMINAL_STATES:
            keep.add(feature["slug"])
            continue
        if cutoff and closed_at(path, feature["id"]) > cutoff:
            keep.add(feature["slug"])
    moved, target = feature_archive.archive(path, feature_archive.archive_dir_for(path), keep=keep)
    if not moved:
        print("docket: 0 feature events archived")
        return 0
    print(f"docket: archived {moved} feature event(s) to {target}")
    return 0


__all__ = ["archived", "closed_at", "cmd_feature_gc", "cmd_feature_remap"]
