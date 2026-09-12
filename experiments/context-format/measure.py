#!/usr/bin/env python3
"""Character and token cost of each briefing variant.

A token count compares format density. It cannot decide whether a format helps
an agent; that needs a comprehension test this repository does not have.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from docket_config import DEFAULTS, merge
from docket_context import build_context
from docket_ledger import project, read


def tokens(text: str) -> str:
    try:
        import tiktoken
    except ImportError:
        return "-"
    return str(len(tiktoken.get_encoding("cl100k_base").encode(text)))


def main() -> int:
    ledger = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".docket/ledger.jsonl"
    entries = project(read(ledger))
    if not entries:
        print(f"no records in {ledger}", file=sys.stderr)
        return 1
    tight = merge({"budget": {"target": DEFAULTS["budget"]["target"] // 2}})
    variants = {
        "scoped": {"files": ("lib/docket_context.py",)},
        "scoped tight": {"files": ("lib/docket_context.py",), "settings": tight},
        "unscoped": {},
        "all": {"all_records": True},
    }
    print(f"{'variant':<14}{'chars':>8}{'tokens':>8}{'full':>6}")
    for name, kwargs in variants.items():
        out = build_context(entries, ledger=str(ledger), **kwargs)
        print(f"{name:<14}{len(out):>8}{tokens(out):>8}{out.count('### '):>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
