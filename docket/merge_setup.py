"""Wire the ledger merge driver into a clone.

The attribute line is committed, but git reads a driver's command only from
git config, never from the repository, so every clone needs `docket init`.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

ATTRIBUTE = ".docket/ledger.jsonl merge=docket"
# docket on PATH, never an absolute path: the plugin cache path changes with
# every release, and a config naming a deleted version fails every merge.
DRIVER = "docket merge-driver %O %A %B"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _in_repository(root: Path) -> bool:
    result = _git(root, "rev-parse", "--git-dir")
    return result is not None and result.returncode == 0


def _has_attribute(root: Path) -> bool:
    path = root / ".gitattributes"
    if not path.is_file():
        return False
    return ATTRIBUTE in (line.strip() for line in path.read_text(encoding="utf-8").splitlines())


def setup(root: Path) -> list[str]:
    """Add the attribute line and register the driver; return what to tell the user."""

    if not _in_repository(root):
        return []
    messages: list[str] = []
    if not _has_attribute(root):
        path = root / ".gitattributes"
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if text and not text.endswith("\n"):
            text += "\n"
        # Appended, not substituted: a later matching line overrides an earlier
        # one, so a .docket/*.jsonl union line keeps covering features.jsonl.
        path.write_text(text + ATTRIBUTE + "\n", encoding="utf-8")
        messages.append(f"docket: added the ledger merge driver to {path}; commit it")
    if shutil.which("docket") is None:
        messages.append(
            "docket: merge driver not registered: docket is not on PATH, so git could not run it. "
            "Put docket on PATH and run docket init again."
        )
        return messages
    _git(root, "config", "--local", "merge.docket.name", "docket ledger merge")
    _git(root, "config", "--local", "merge.docket.driver", DRIVER)
    messages.append("docket: registered the ledger merge driver in this clone's git config")
    return messages


def notice(root: Path) -> str | None:
    """One briefing line when the repository asks for the driver and this clone lacks it."""

    try:
        if not _has_attribute(root) or not _in_repository(root):
            return None
        result = _git(root, "config", "--get", "merge.docket.driver")
        command = result.stdout.strip() if result is not None and result.returncode == 0 else ""
        words = shlex.split(command) if command else []
        if words and shutil.which(words[0]):
            return None
    except (OSError, ValueError):
        return None
    return "# merge driver not set up in this clone; run docket init"


__all__ = ["ATTRIBUTE", "DRIVER", "notice", "setup"]
