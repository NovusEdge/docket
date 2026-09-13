"""The docket package: ledger, context, config, migrate, rebase, update.

Imports no submodule, so importing one never pulls the rest. A SessionStart
hook runs this on every session.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def version() -> str:
    """The release, from the VERSION file beside the checkout.

    Read only when a version or top-level help request asks for it. The
    SessionStart hook runs `context` on every session and must not pay for a
    file read it never uses.
    """
    try:
        return (ROOT / "VERSION").read_text().strip()
    except OSError:
        return "unknown"
