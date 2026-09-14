#!/usr/bin/env python3
"""Repoint this project's ledger scopes at the docket package.

Scope decides which records a briefing surfaces, so the lib/ to docket/ rename
left 35 scope entries matching nothing. This rewrites them in place after
writing a backup beside the ledger.

One-off, for this repository. Another project's ledger names its own
directories, so nothing here generalises into a docket subcommand.

Run from the repository root:

    python3 scripts/rescope_ledger.py --dry-run
    python3 scripts/rescope_ledger.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

LEDGER = Path(".docket/ledger.jsonl")
BACKUP = Path(".docket/ledger-prepackage-backup.jsonl")

# Mechanical: the module moved, so the scope follows it.
PATHS = {
    "lib/**": "docket/**",
    "lib/docket_context.py": "docket/context.py",
    "lib/docket_ledger.py": "docket/ledger.py",
    "lib/docket_config.py": "docket/config.py",
    "lib/docket_migrate.py": "docket/migrate.py",
    "lib/docket_rebase.py": "docket/rebase.py",
    "lib/docket_update.py": "docket/update.py",
}

# bin/docket still exists as the launcher, so the right target depends on what
# each record is about. Routed by hand, by reading each one. A record absent
# from this table keeps bin/docket: d80 and d82 both decide what the entry
# point is, which is still this file.
BIN_ROUTES = {
    "d12": "docket/env.py",  # where the ledger lives by default
    "d13": "docket/env.py",  # provenance capture
    "q15": "docket/env.py",  # justification sets
    "c20": "docket/env.py",  # retirement reporting
    "d78": "docket/cli/query.py",  # the update notice line
    "d36": "docket/cli/graph.py",  # graph browsing
    "d77": "docket/cli/admin.py",  # the update command
    "d14": "docs/installation.md",  # which harnesses ship config
    # Nothing in the CLI: d16 puts defects in GitHub issues, and d43, d44 and
    # d45 decide the record and context model, which docket/** already covers.
    "d16": None,
    "d43": None,
    "d44": None,
    "d45": None,
}

# The first run routed d14, d16, d43, d44 and d45 by mechanical assignment
# instead of by subject, so it sent them to the CLI. Re-running is idempotent
# for every other record; these five need the wrong target taken back out.
FIRST_RUN_MISTAKES = {
    "d14": "docket/cli/query.py",
    "d16": "docket/cli/**",
    "d43": "docket/cli/**",
    "d44": "docket/cli/**",
    "d45": "docket/cli/**",
}


def rescope(entry: dict) -> list[str] | None:
    """The record's new scope, or None when nothing changes."""
    old = entry.get("scope") or []
    wrong = FIRST_RUN_MISTAKES.get(entry["id"])
    new: list[str] = []
    for item in old:
        if item == wrong:
            continue
        if item in PATHS:
            new.append(PATHS[item])
        elif item == "bin/docket":
            target = BIN_ROUTES.get(entry["id"], "bin/docket")
            if target is not None:
                new.append(target)
        else:
            new.append(item)
    # The first run already consumed this record's bin/docket entry, so the
    # corrected target has to be added rather than substituted.
    if wrong is not None:
        target = BIN_ROUTES.get(entry["id"])
        if target is not None:
            new.append(target)
    # Routing can collide with a scope the record already carries.
    new = list(dict.fromkeys(new))
    return new if new != old else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print the changes and write nothing"
    )
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args(argv)

    if not args.ledger.exists():
        print(f"rescope: {args.ledger} does not exist", file=sys.stderr)
        return 1

    lines = args.ledger.read_text().splitlines()
    out: list[str] = []
    changed = 0
    for line in lines:
        entry = json.loads(line)
        new = rescope(entry)
        if new is None:
            out.append(line)
            continue
        changed += 1
        print(f"{entry['id']:5} {entry.get('scope')} -> {new}")
        entry["scope"] = new
        out.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))

    unrouted = sorted(
        json.loads(line)["id"]
        for line in lines
        if "bin/docket" in (json.loads(line).get("scope") or [])
        and json.loads(line)["id"] not in BIN_ROUTES
    )
    if unrouted:
        print(f"\nkept bin/docket, decided by hand: {', '.join(unrouted)}")

    if not changed:
        print("rescope: nothing to change")
        return 0
    if args.dry_run:
        print(f"\nrescope: {changed} records would change; wrote nothing")
        return 0

    shutil.copy2(args.ledger, BACKUP)
    args.ledger.write_text("\n".join(out) + "\n")
    print(f"\nrescope: rewrote {changed} records; backup at {BACKUP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
