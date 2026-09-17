"""Where the ledger lives, and who is writing to it.

Environment and path resolution, kept apart from the CLI so every command group
reaches it the same way.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from docket.ledger import read as ledger_read

LEDGER = Path(".docket/ledger.jsonl")


# Honours XDG so the global store can be relocated, and CLAUDE_CONFIG_DIR so an
# isolated Claude profile gets its own ledgers.
def global_root() -> Path:
    if env := os.environ.get("DOCKET_HOME"):
        return Path(env).expanduser()
    if env := os.environ.get("CLAUDE_CONFIG_DIR"):
        return Path(env).expanduser() / "docket"
    return Path.home() / ".claude" / "docket"


def session_id() -> str:
    """Claude Code exposes this under more than one name across versions."""
    for var in ("CLAUDE_SESSION_ID", "CLAUDE_CODE_BRIDGE_SESSION_ID", "SESSION_ID"):
        if v := os.environ.get(var):
            return v
    return ""


def author() -> str:
    """Which agent or person recorded the entry.

    Two agents sharing one ledger is the normal case, so an entry that does not
    say who wrote it cannot be weighed.
    """
    if v := os.environ.get("DOCKET_AUTHOR"):
        return v
    if v := os.environ.get("AI_AGENT"):
        return v.split("_")[0]
    if os.environ.get("CODEX_SANDBOX") or os.environ.get("CODEX_HOME"):
        return "codex"
    return os.environ.get("USER", "")


def resolved_author() -> str:
    """author(), falling back to a visible "unknown" instead of silence.

    A blank string is indistinguishable from an unset field once serialized, so
    a caller reading the ledger cannot tell "detection failed" from "this entry
    predates the author field". Writing "unknown" makes the failure visible;
    the missing key on old entries stays the only true absence.
    """
    a = author()
    if a:
        return a
    print(
        'docket: could not detect an author; recording "unknown". '
        "Set DOCKET_AUTHOR to identify this harness.",
        file=sys.stderr,
    )
    return "unknown"


def branch(root: Path) -> str:
    """Current branch, or empty outside a repository.

    Uses `branch --show-current` because `rev-parse --abbrev-ref HEAD` fails on
    an unborn branch, which is every repository before its first commit.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def project_root(start: Path | None = None) -> Path:
    """The directory a project-local ledger belongs to.

    Prefers the git root so a subdirectory shares the project's ledger. Falls
    back to the working directory outside a repository.
    """
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / ".git").exists():
            return d
    return here


def slug(path: Path) -> str:
    """Mangle an absolute path into one filename component."""
    return str(path).replace("/", "-").replace("\\", "-").strip("-") or "root"


def ledger_path(start: Path | None = None) -> Path:
    """Resolve the ledger for the current project.

    A .docket directory in the project wins, which is how a team opts into
    committing decisions. Otherwise the ledger lives under the global root,
    keyed by project path, so a new project needs no setup and no gitignore
    entry.
    """
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        candidate = d / LEDGER
        if candidate.exists():
            return candidate
    return global_root() / slug(project_root(here)) / "ledger.jsonl"


def features_path(start: Path | None = None) -> Path:
    """The feature store, always beside the ledger it accompanies.

    One store location, never split: docket init moves both files together.
    """
    return ledger_path(start).parent / "features.jsonl"


def read(path: Path, lock: bool = True) -> list[dict]:
    return ledger_read(path, lock=lock)


def justification_sets(e: dict) -> list[list[str]]:
    return e.get("supports", [])


def retired_by(entries: list[dict]) -> dict[str, str]:
    """Map each superseded ID to its replacement.

    Tolerates a raw entry, unlike docket.ledger.retired_by, which subscripts
    "supersedes" and raises KeyError on anything project() has not filled in.
    Callers here pass read() output straight through.
    """
    return {target: e["id"] for e in entries for target in e.get("supersedes", [])}
