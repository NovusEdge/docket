"""A git merge driver for the ledger.

Git hands a merge driver three temp files and keeps whatever the second one
holds. On a non-zero exit it marks the path unmerged but still takes that
file as the worktree version, so a failure must leave conflict markers in it:
an untouched OURS would look like a clean ledger, and staging it would drop
every incoming record.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from docket import env, feature_project, features, ledger, rebase
from docket.feature_archive import highest_archived_id


def _conflict(base: Path, ours: Path, theirs: Path) -> None:
    try:
        original = ours.read_bytes()
        incoming = theirs.read_bytes()
    except OSError:
        return
    status = None
    try:
        status = subprocess.run(
            [
                "git",
                "merge-file",
                "-L",
                "ours",
                "-L",
                "base",
                "-L",
                "theirs",
                str(ours),
                str(base),
                str(theirs),
            ],
            capture_output=True,
            timeout=30,
        ).returncode
    except (OSError, subprocess.SubprocessError):
        print("docket: git merge-file could not run; wrote whole-file markers", file=sys.stderr)
    # merge-file exits with the conflict count (1..127); 0 means it merged the
    # text cleanly, which the driver's own refusal overrides, and anything else
    # is a failure that may have left OURS untouched.
    if status is not None and 0 < status < 128:
        return
    block = b"<<<<<<< ours\n" + _terminated(original) + b"=======\n"
    block += _terminated(incoming) + b">>>>>>> theirs\n"
    try:
        ours.write_bytes(block)
    except OSError as exc:
        print(f"docket: cannot write conflict markers: {exc}", file=sys.stderr)


def _terminated(data: bytes) -> bytes:
    return data if not data or data.endswith(b"\n") else data + b"\n"


def _holds_features(*paths: Path) -> bool:
    """Whether these are feature stores rather than ledgers.

    Git hands the driver temp files with no path, so the first line decides:
    a feature event carries "event", a ledger record does not.
    """
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for line in lines:
            if line.strip():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    break
                return isinstance(value, dict) and "event" in value
    return False


def _feature_tail(
    base: list[dict[str, Any]], ours: list[dict[str, Any]], theirs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """THEIRS events to append to OURS, under ids that do not collide.

    The same match-then-renumber as rebase.merge: an event equal to one of
    ours apart from its id is already here, and one equal to a base event was
    dropped on our side. Feature events cite each other by slug, never by
    id, so renumbering needs no rewriting.
    """

    def key(event: dict[str, Any]) -> str:
        return json.dumps({k: v for k, v in event.items() if k != "id"}, sort_keys=True)

    shared = rebase.common_prefix(ours, theirs)
    waiting: dict[str, int] = {}
    for event in ours[shared:]:
        waiting[key(event)] = waiting.get(key(event), 0) + 1
    in_base = {key(event) for event in base}
    # git runs a merge driver from the top of the work tree, where
    # features_path finds the store whose archive holds retired ids.
    floor = highest_archived_id(env.features_path())
    allocated = list(ours)
    tail = []
    for event in theirs[shared:]:
        k = key(event)
        if waiting.get(k):
            waiting[k] -= 1
            continue
        if k in in_base:
            continue
        renumbered = dict(event, id=features.next_id(allocated, floor))
        allocated.append(renumbered)
        tail.append(renumbered)
    feature_project.project(ours + tail)
    return tail


def run(base: Path, ours: Path, theirs: Path) -> int:
    """Merge THEIRS into OURS in place. 0 when merged, 1 when left in conflict."""

    moved: dict[str, str] = {}
    try:
        if _holds_features(base, ours, theirs):
            old, mine, incoming = (features.read(p, lock=False) for p in (base, ours, theirs))
            tail = _feature_tail(old, mine, incoming)
        else:
            # lock=False: the default lock creates <file>.lock next to git's
            # temp files at the repository root, where nothing ignores it.
            old, mine, incoming = (
                ledger.read(p, lock=False, strict=True) for p in (base, ours, theirs)
            )
            tail, moved = rebase.merge(old, mine, incoming)
            ledger.validate_entries(mine + tail)
    except (ledger.LedgerError, rebase.RebaseError, features.FeatureError, OSError) as exc:
        print(f"docket: cannot merge {ours.name}: {exc}", file=sys.stderr)
        _conflict(base, ours, theirs)
        return 1
    if tail:
        lines = "".join(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in tail
        )
        with ours.open("rb") as handle:
            handle.seek(0, 2)
            needs_newline = False
            if handle.tell():
                handle.seek(-1, 2)
                needs_newline = handle.read(1) != b"\n"
        with ours.open("a", encoding="utf-8", newline="") as handle:
            handle.write(("\n" if needs_newline else "") + lines)
    for old_id, new_id in moved.items():
        if old_id != new_id:
            print(f"docket: {old_id} -> {new_id}", file=sys.stderr)
    return 0


__all__ = ["run"]
