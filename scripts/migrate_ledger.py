#!/usr/bin/env python3
"""Command-line entry point for the schema-1 to schema-2 ledger migration.

The implementation lives in docket/ because an installed Docket ships docket/
and bin/ only. This file stays so the documented invocation keeps working.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from docket.migrate import main  # noqa: E402
except ImportError as exc:  # pragma: no cover - a broken or partial install
    # docket.migrate pulls docket.ledger at module scope. Report which import
    # failed instead of printing a traceback at someone mid-migration.
    print(f"migrate_ledger: cannot import docket.migrate: {exc}", file=sys.stderr)
    raise SystemExit(1) from None


if __name__ == "__main__":
    raise SystemExit(main())
