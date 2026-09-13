"""Update state and version comparison. Standard library only, because the
SessionStart hook imports this on every session."""

from __future__ import annotations

import json
import os
import subprocess
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
    except OSError:
        return
    try:
        with os.fdopen(handle, "w") as out:
            json.dump(data, out)
        # os.replace is atomic and overwrites an existing file on Windows,
        # where a plain rename onto one fails.
        os.replace(temporary, state_path())
    except OSError:
        pass
    finally:
        Path(temporary).unlink(missing_ok=True)


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


RELEASES_URL = "https://api.github.com/repos/NovusEdge/docket/releases/latest"
FETCH_TIMEOUT = 5.0
DISABLE_ENV = "DOCKET_NO_UPDATE_CHECK"


def disabled() -> bool:
    return os.environ.get(DISABLE_ENV, "") not in ("", "0")


def due(state: dict, now: float) -> bool:
    try:
        return now >= float(state.get("next_check_at", 0))
    except (TypeError, ValueError):
        return True


def fetch_latest(url: str = RELEASES_URL) -> str:
    from urllib.request import urlopen

    with urlopen(url, timeout=FETCH_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag = payload.get("tag_name", "")
    if not isinstance(tag, str) or not tag:
        raise ValueError("release payload carries no tag_name")
    return tag


def run_fetch(now: float) -> int:
    state = read_state()
    # The lease lands before the request, so a second session starting while
    # this one waits on the network sees a future next_check_at and does not
    # fork a second fetcher.
    write_state({**state, "next_check_at": now + LEASE_SECONDS})
    try:
        latest = fetch_latest()
    except Exception:
        failures = int(state.get("failures", 0) or 0) + 1
        delay = min(FAILURE_SECONDS * (2 ** (failures - 1)), FAILURE_CAP)
        write_state({**state, "failures": failures, "next_check_at": now + delay})
        return 1
    write_state({"latest": latest, "checked_at": now, "failures": 0,
                 "next_check_at": now + SUCCESS_SECONDS})
    return 0


def spawn_fetch(script: Path) -> None:
    """Start the refresh and return. The parent never waits.

    Every stream goes to devnull. A child that inherits the hook's stdout
    holds the pipe open after the hook exits, so the harness reads to EOF and
    stalls for the whole hook timeout, and anything the child prints lands in
    the session context outside the JSON envelope.
    """
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, str(script), "_update-fetch"], **kwargs)
    except OSError:
        return
