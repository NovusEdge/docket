#!/usr/bin/env python3
"""Command-line entry point for the schema-1 to schema-2 ledger migration.

The implementation lives in lib/ because an installed Docket ships lib/ and
bin/ only. This file stays so the documented invocation keeps working.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.docket_migrate import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
