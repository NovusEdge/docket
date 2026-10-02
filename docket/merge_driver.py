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

from docket import ledger, rebase


def _conflict(base: Path, ours: Path, theirs: Path) -> None:
    try:
        subprocess.run(
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
        )
    except (OSError, subprocess.SubprocessError):
        pass


def run(base: Path, ours: Path, theirs: Path) -> int:
    """Merge THEIRS into OURS in place. 0 when merged, 1 when left in conflict."""

    try:
        # lock=False: the default lock creates <file>.lock next to git's temp
        # files at the repository root, where nothing ignores it.
        old, mine, incoming = (ledger.read(p, lock=False) for p in (base, ours, theirs))
        tail, moved = rebase.merge(old, mine, incoming)
        ledger.validate_entries(mine + tail)
    except (ledger.LedgerError, rebase.RebaseError, OSError) as exc:
        print(f"docket: cannot merge the ledger: {exc}", file=sys.stderr)
        _conflict(base, ours, theirs)
        return 1
    if tail:
        text = ours.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            text += "\n"
        text += "".join(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in tail
        )
        ours.write_text(text, encoding="utf-8")
    for old_id, new_id in moved.items():
        if old_id != new_id:
            print(f"docket: {old_id} -> {new_id}", file=sys.stderr)
    return 0


__all__ = ["run"]
