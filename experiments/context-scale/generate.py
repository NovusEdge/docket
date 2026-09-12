#!/usr/bin/env python3
"""Briefing cost against ledger size.

Every threshold in the scale plan is chosen against this table. Re-run it after
changing the index cap or the scoring, and record the new numbers in README.md.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from docket_context import build_context
from docket_ledger import make_record, project

AREAS = ("lib", "bin", "docs", "installer", "graph", "tests")

INDEX_LINE = re.compile(r"^[cdq]\d+ (?:claim|decision|question) ", re.M)


def ledger(count: int) -> list[dict]:
    records = []
    for index in range(1, count + 1):
        area = AREAS[index % len(AREAS)]
        if index % 3 == 0:
            record = make_record(
                "decision", f"Decision {index} about {area}", choice=f"option {index}",
                scope=[f"{area}/**"], author="bench", record_id=f"d{index}",
                depends_on=[f"c{index - 1}"] if index > 3 else [],
            )
        else:
            record = make_record(
                "claim", f"Claim {index} about {area}", state="accepted",
                scope=[f"{area}/**"], author="bench", record_id=f"c{index}",
            )
        records.append(record)
    return records


def main() -> int:
    print(f"{'records':>8}{'unscoped':>10}{'scoped':>9}{'full':>6}{'index':>7}")
    for count in (33, 100, 250, 500, 1000):
        history = project(ledger(count))
        unscoped = build_context(history, ledger="bench")
        scoped = build_context(history, files=("lib/render.py",), ledger="bench")
        full = scoped.count("### ")
        index = len(INDEX_LINE.findall(scoped))
        print(f"{count:>8}{len(unscoped):>10}{len(scoped):>9}{full:>6}{index:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
