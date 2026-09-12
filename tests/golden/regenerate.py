"""Build the golden briefings that pin `build_context` output.

Run this file to rewrite context_snapshots.json. Do that only when a change is
meant to alter what a briefing says.
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.test_context import entry, projected
from lib.docket_context import build_context

SEED = 20260913


def ledger(count):
    random.seed(SEED + count)
    records = []
    for number in range(1, count + 1):
        kind = ("decision", "claim", "question")[number % 3]
        fields = {"choice": f"Choice {number}"} if kind == "decision" else {}
        if kind == "decision" and number > 3 and random.random() < 0.6:
            target, target_kind = records[random.randrange(len(records))]
            if target_kind in ("claim", "decision"):
                fields["depends_on"] = (target,)
        ident = f"{kind[0]}{number}"
        records.append((ident, kind))
        yield entry(ident, kind, f"Record {ident} about module {number % 7}",
                    scope=(f"lib/mod{number % 7}/**",), **fields)


def snapshots():
    cases = {}
    for count in (5, 60, 400, 1500):
        projected_records = projected(list(ledger(count)))
        for query, files in (("", ()), ("module 3", ()), ("", ("lib/mod3/cache.py",))):
            for budget in (900, 8000):
                key = f"n{count}_q{query or 'none'}_f{'yes' if files else 'no'}_b{budget}"
                cases[key] = build_context(projected_records, query=query, files=files,
                                           ledger="repo", max_chars=budget)
    return cases


if __name__ == "__main__":
    target = Path(__file__).parent / "context_snapshots.json"
    target.write_text(json.dumps(snapshots(), indent=0))
    print(f"wrote {target}")
