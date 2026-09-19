"""docket update: replace this copy of docket with a newer one.

Split from docket.cli.admin to keep that file under the 300 line limit. Every
other command there repairs or inspects a ledger. This one runs an installer.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from docket import ROOT, version

LAUNCHER_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/NovusEdge/docket/refs/tags/{tag}/installer/install.py"
)
MAIN_LAUNCHER_URL = "https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py"


def cmd_update(args: argparse.Namespace, root: Path | None = None) -> int:
    from docket.update import is_newer, parse_version, read_state, shape, update_command

    # ROOT, never __file__: this module sits two levels below the checkout, so
    # parent.parent would name docket/ and update_command would print a path
    # that does not exist.
    root = root or ROOT
    running = version()
    latest = str(read_state().get("latest", ""))
    if args.check:
        if not latest or parse_version(latest) is None:
            print("docket: no cached release information yet")
            return 2
        if is_newer(latest, running):
            print(f"docket {latest.lstrip('v')} is available (running {running})")
            return 1
        print(f"docket {running} is up to date")
        return 0

    kind = shape(root)
    if kind == "plugin":
        print(f"docket: this copy is managed by your harness. Run: {update_command(root)}")
        return 0
    if kind == "unknown":
        print(f"docket: this copy has no installer and no repository. Run: {update_command(root)}")
        return 0
    if kind == "source":
        command = [
            sys.executable,
            str(root / "installer" / "install.py"),
            "--checkout",
            str(root),
            "--update",
        ]
        print(" ".join(command))
        return subprocess.call(command)
    tag = latest if latest and parse_version(latest) is not None else None
    return _run_downloaded_update(tag, root)


def _managed_prefix(root: Path) -> str:
    """The command directory this checkout was installed under, or "".

    The installer writes the prefix into .docket-managed, and --update
    validates the installed command against the checkout it pairs with. The
    downloaded launcher runs outside the checkout and cannot find either one
    on its own, so both travel as arguments.
    """
    try:
        marker = json.loads((root / ".docket-managed").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    prefix = marker.get("prefix") if isinstance(marker, dict) else None
    return prefix if isinstance(prefix, str) else ""


def _run_downloaded_update(tag: str | None, root: Path) -> int:
    """Fetch the launcher and run it outside the checkout.

    The bundled launcher takes its own checkout branch, which needs Go and
    passes --checkout, and --checkout makes the planner skip the git update.
    Without a cached release tag, fall back to the main branch so a fresh
    install (no cache populated yet) can still update.
    """
    from urllib.request import urlopen

    url = LAUNCHER_URL_TEMPLATE.format(tag=tag) if tag else MAIN_LAUNCHER_URL
    with tempfile.TemporaryDirectory() as work:
        launcher = Path(work) / "install.py"
        try:
            with urlopen(url, timeout=30) as response:
                launcher.write_bytes(response.read())
        except OSError as exc:
            print(f"docket: could not download the installer: {exc}", file=sys.stderr)
            return 1
        command = [sys.executable, str(launcher), "--update", "--dir", str(root)]
        if prefix := _managed_prefix(root):
            command += ["--prefix", prefix]
        print(" ".join(command))
        return subprocess.call(command, cwd=work)


def cmd_update_fetch(args: argparse.Namespace) -> int:
    from docket.update import run_fetch

    return run_fetch(time.time())


__all__ = ["cmd_update", "cmd_update_fetch"]
