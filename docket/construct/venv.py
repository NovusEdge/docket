"""Construct's private virtualenv: where the provider SDK lives.

Outside the checkout, under the global store. The installer replaces a managed
checkout wholesale on reinstall and keeps only `.docket`, so a venv inside it
would not survive. Standard library only, like every other module a CLI command
body reaches.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

from docket.env import global_root

# Bounded majors. A reinstall re-resolves, and a new major arriving that way
# would change the request shape under a command nobody was upgrading.
SPECS = {
    "openai": "openai>=2,<3",
    "anthropic": "anthropic>=1,<2",
}


class VenvError(RuntimeError):
    """The venv could not be built, and the message says what to do about it."""


def root() -> Path:
    return global_root() / "venv"


def interpreter() -> Path:
    if os.name == "nt":
        return root() / "Scripts" / "python.exe"
    return root() / "bin" / "python"


def packages() -> Path:
    """The venv's site-packages for the interpreter running right now.

    The path carries this interpreter's `pythonX.Y`, so a venv built before a
    distro upgraded Python resolves to a directory that does not exist. That is
    the staleness check: `activate` reports False and the user rebuilds.
    """
    base = str(root())
    return Path(sysconfig.get_path("purelib", "venv", vars={"base": base, "platbase": base}))


def activate() -> bool:
    """Put the venv on the import path, and report whether it was there.

    Appended, never inserted. Someone who installed the SDK into their own
    environment keeps that copy.
    """
    site = packages()
    if not site.is_dir():
        return False
    if str(site) not in sys.path:
        sys.path.append(str(site))
    return True


def install(package: str) -> Path:
    """Build the venv if needed and put one package in it. Returns its root."""
    spec = SPECS.get(package, package)
    if shutil.which("uv") is None:
        raise VenvError(
            "docket construct installs its SDK with uv, which is not on PATH. "
            "Install uv (https://docs.astral.sh/uv/), or install "
            f"{spec!r} into a virtualenv yourself."
        )

    # --python pins the venv to the interpreter running docket. Without it uv
    # may build against a Python it downloaded, and the compiled dependencies
    # would not import into this process.
    _run(["uv", "venv", "--python", sys.executable, "--allow-existing", str(root())])
    _run(["uv", "pip", "install", "--python", str(interpreter()), spec])
    return root()


def remove() -> None:
    shutil.rmtree(root(), ignore_errors=True)


def _run(argv: list[str]) -> None:
    try:
        done = subprocess.run(argv, capture_output=True, text=True)
    except OSError as exc:
        raise VenvError(f"{argv[0]} could not run: {exc}") from None
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "").strip()
        raise VenvError(f"{' '.join(argv[:2])} failed: {detail}")
