"""Update state and version comparison. Standard library only, because the
SessionStart hook imports this on every session."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

LEASE_SECONDS = 300
SUCCESS_SECONDS = 86400
FAILURE_SECONDS = 3600
FAILURE_CAP = 86400


def state_dir(platform: str | None = None) -> Path:
    platform = platform or sys.platform
    if platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            # Not %LOCALAPPDATA%\docket: that is the default managed checkout,
            # and state inside a git work tree the installer updates is lost.
            return Path(local) / "docket-state"
    if xdg := os.environ.get("XDG_STATE_HOME"):
        return Path(xdg) / "docket"
    return Path.home() / ".local" / "state" / "docket"


def state_path() -> Path:
    return state_dir() / "update.json"


def read_state() -> dict:
    try:
        data = json.loads(state_path().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(data: dict) -> None:
    directory = state_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(handle, "w") as out:
            json.dump(data, out)
        # os.replace is atomic and overwrites an existing file on Windows,
        # where a plain rename onto one fails.
        os.replace(temporary, state_path())
    except OSError:
        return


def parse_version(text: str) -> tuple[int, int, int] | None:
    parts = text.strip().lstrip("v").split(".")
    if len(parts) < 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2].split("-")[0])
    except ValueError:
        return None


def is_newer(latest: str, running: str) -> bool:
    left, right = parse_version(latest), parse_version(running)
    if left is None or right is None:
        return False
    return left > right


REPOSITORY = "https://github.com/NovusEdge/docket"

_HARNESS_ANCHORS = ((".claude", "claude"), (".codex", "codex"))


def plugin_origin(root: Path) -> tuple[str, str] | None:
    """(harness, marketplace) when root is a harness plugin cache copy.

    Both harnesses lay the cache out as .../plugins/cache/<marketplace>/
    <plugin>/<version>, so the anchor directory is what tells them apart.
    """
    parts = root.parts
    if "plugins" not in parts:
        return None
    index = parts.index("plugins")
    tail = parts[index + 1:]
    if len(tail) < 2 or tail[0] != "cache":
        return None
    marketplace = tail[1]
    for anchor, harness in _HARNESS_ANCHORS:
        if anchor in parts[:index]:
            return harness, marketplace
    return None


def shape(root: Path) -> str:
    # The marker is tested first because a managed checkout is a git clone,
    # so a .git test would classify every managed install as a source tree.
    if (root / ".docket-managed").exists():
        return "managed"
    if plugin_origin(root):
        return "plugin"
    if (root / ".git").exists():
        return "source"
    return "unknown"


def update_command(root: Path) -> str:
    origin = plugin_origin(root)
    if origin:
        harness, marketplace = origin
        if harness == "claude":
            return (f"claude plugin update docket@{marketplace} -y, "
                    "then restart Claude Code")
        return (f"codex plugin remove docket@{marketplace} && "
                f"codex plugin add docket@{marketplace}")
    if shape(root) == "unknown":
        return f"reinstall from {REPOSITORY}"
    return "docket update"


def notice(running: str, latest: str, root: Path) -> str | None:
    if not latest or not is_newer(latest, running):
        return None
    tag = latest.lstrip("v")
    return (f"# docket: {tag} is available (running {running}). "
            f"Run: {update_command(root)}")
