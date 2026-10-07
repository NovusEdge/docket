"""A git merge driver for the ledger.

Git hands a merge driver three temp files and keeps whatever the second one
holds. On a non-zero exit it marks the path unmerged but still takes that
file as the worktree version, so a failure must leave conflict markers in it:
an untouched OURS would look like a clean ledger, and staging it would drop
every incoming record. A refusal for mixed schemas counts as a failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from docket import env, feature_project, features, ledger, migrate, rebase
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
        # Ledger ids, their keys and the schema differ between copies of one
        # event that two branches migrated separately, or that BASE still
        # holds at features schema 1. ts, author, session and text still tell
        # two recordings apart.
        skip = {"id", "schema", "keys", *features.LEDGER_REFS}
        return json.dumps({k: v for k, v in event.items() if k not in skip}, sort_keys=True)

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


def _first_schema(path: Path) -> Any:
    """The schema of the first line, 1 when it declares none, None when unreadable or empty."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for line in lines:
        if line.strip():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                return None
            return value.get("schema", 1) if isinstance(value, dict) else None
    return None


def _raw(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _base_ledger(path: Path) -> list[dict[str, Any]]:
    """BASE, upgraded in memory when it is one schema behind.

    Only the matching in rebase.merge reads it, and both branches migrated from
    this same file, so renumbering it gives the ids they now share. It is never
    written back.
    """
    if _first_schema(path) == ledger.SCHEMA - 1:
        return migrate.renumber_step(_raw(path))[0]
    return ledger.read(path, lock=False, strict=True)


def _behind(ours: Path, theirs: Path, current: int) -> tuple[str, int] | None:
    for label, path in (("this branch's", ours), ("the other branch's", theirs)):
        schema = _first_schema(path)
        if isinstance(schema, int) and schema < current:
            return label, schema
    return None


def run(base: Path, ours: Path, theirs: Path) -> int:
    """Merge THEIRS into OURS in place. 0 when merged, 1 when left in conflict or refused."""

    moved: dict[str, str] = {}
    holds_features = _holds_features(base, ours, theirs)
    behind = _behind(ours, theirs, features.SCHEMA if holds_features else ledger.SCHEMA)
    if behind:
        side, schema = behind
        noun = "features file" if holds_features else "ledger"
        print(
            f"docket: cannot merge {ours.name}: {side} {noun} is schema {schema}; "
            "run docket migrate on it, commit, and merge again",
            file=sys.stderr,
        )
        _conflict(base, ours, theirs)
        return 1
    try:
        if holds_features:
            mine, incoming = (features.read(p, lock=False) for p in (ours, theirs))
            # BASE is read raw: it may still be schema 1, and only matching uses it.
            tail = _feature_tail(_raw(base), mine, incoming)
        else:
            # lock=False: the default lock creates <file>.lock next to git's
            # temp files at the repository root, where nothing ignores it.
            old = _base_ledger(base)
            mine, incoming = (ledger.read(p, lock=False, strict=True) for p in (ours, theirs))
            tail, moved = rebase.merge(old, mine, incoming)
            ledger.validate_entries(mine + tail)
    except (
        ledger.LedgerError,
        rebase.RebaseError,
        features.FeatureError,
        json.JSONDecodeError,
        OSError,
        # BASE is read raw: a non-UTF-8 file or a line that is JSON but not an object.
        UnicodeError,
        AttributeError,
        TypeError,
    ) as exc:
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
