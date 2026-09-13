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
