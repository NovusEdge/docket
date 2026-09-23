"""Commands that repair or inspect a store: rebase, migrate, check, init.

docket completion and docket update live in docket.cli.completion and
docket.cli.selfupdate, which keeps this file under the 300 line limit. Neither
of those reads a ledger.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docket import env, feature_archive, feature_project, features
from docket.ledger import ID_RE, LedgerError, _Prefix, append, validate_record


def cmd_rebase(args: argparse.Namespace) -> int:
    """Append another branch's divergent tail under fresh IDs."""
    from docket.rebase import RebaseError, renumber

    path = env.ledger_path()
    other = Path(args.other)
    if not other.is_file():
        print(f"docket: no ledger at {other}", file=sys.stderr)
        return 1
    try:
        mine = env.read(path)
        theirs = env.read(other)
        tail, mapping = renumber(mine, theirs)
    except (LedgerError, RebaseError, OSError) as exc:
        print(f"docket: {exc}", file=sys.stderr)
        return 1
    if not tail:
        print("docket: nothing to rebase; the histories already agree")
        return 0
    for old, new in mapping.items():
        print(f"{old} -> {new}")
    if args.emit_map:
        Path(args.emit_map).write_text(json.dumps(mapping), encoding="utf-8")
    if args.dry_run:
        print(f"\ndocket: {len(tail)} record(s) would be appended to {path}")
        return 0
    # append validates each record against everything already written, so a
    # tail that would break the ledger stops partway and leaves it readable.
    written = 0
    try:
        for record in tail:
            append(path, record)
            written += 1
    except LedgerError as exc:
        print(f"docket: {exc}", file=sys.stderr)
        print(
            f"docket: appended {written} of {len(tail)} record(s); run docket check",
            file=sys.stderr,
        )
        return 1
    print(f"\ndocket: appended {written} record(s) to {path}")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Convert this project's ledger to the current schema."""
    from docket.migrate import (
        MigrationError,
        derive_mapping,
        detect_version,
        migrate_in_place,
        read_source,
    )

    path = env.ledger_path()
    if not path.exists():
        print(f"docket: no ledger at {path}")
        return 0
    try:
        if args.emit_map:
            source = read_source(path)
            if detect_version(source) == 2:
                print("docket: already schema 2")
                return 0
            mapping = derive_mapping(source)
            Path(args.emit_map).write_text(
                json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(
                f"docket: wrote {len(mapping)} mapping entr"
                f"{'y' if len(mapping) == 1 else 'ies'} to {args.emit_map}"
            )
            return 0
        count, report, notes = migrate_in_place(path, mapping_path=args.map, dry_run=args.dry_run)
    except MigrationError as exc:
        print(f"docket: {exc}", file=sys.stderr)
        print(
            "docket: to classify records by hand, run 'docket migrate --emit-map FILE', "
            "edit FILE, then 'docket migrate --map FILE'",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        print(f"docket: {exc}", file=sys.stderr)
        return 1
    if not count:
        print("docket: already schema 2")
        return 0
    for note in notes:
        print(f"docket: warning: {note}", file=sys.stderr)
    for line in report:
        print(line)
    if args.dry_run:
        print(f"docket: would convert {count} record{'' if count == 1 else 's'}")
        return 0
    print(
        f"docket: converted {count} record{'' if count == 1 else 's'}; "
        f"original kept at {path}.schema1"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Report every fault in the ledger, rather than the first one.

    read() raises on the first bad line. After a merge a person needs the whole
    picture before deciding how to repair it.
    """
    path = env.ledger_path()
    if not path.exists():
        print(f"docket: no ledger at {path}")
        return 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        print(f"docket: cannot read {path}: {exc}", file=sys.stderr)
        return 1

    faults: list[str] = []
    good: list[dict] = []
    # One index threaded through the loop. Rebuilding it per record made doctor
    # quadratic in ledger size, which is the cost read() and validate_entries
    # already shed.
    prefix = _Prefix([])
    seen: dict[str, int] = {}
    highest = 0
    records = 0
    correction_lines = 0
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            faults.append(f"line {number}: invalid JSON: {exc.msg}")
            continue
        if isinstance(record, dict) and record.get("kind") == "correction":
            correction_lines += 1
            # Kept out of seen: a feature that names a correction id names
            # nothing a brief can attach, and the feature check reports it.
            try:
                checked = validate_record(record, prefix=prefix)
            except LedgerError as exc:
                faults.append(f"line {number}: {str(exc).removeprefix('docket: ')}")
            else:
                prefix.add(checked)
            continue
        records += 1
        ident = str(record.get("id", "")) if isinstance(record, dict) else ""
        match = ID_RE.fullmatch(ident)
        if not match:
            faults.append(f"line {number}: malformed id {ident!r}")
            continue
        if ident in seen:
            faults.append(f"line {number}: duplicate id {ident}, first seen on line {seen[ident]}")
            continue
        seen[ident] = number
        sequence = int(match.group(2))
        if sequence <= highest:
            faults.append(f"line {number}: id {ident} does not increase past {highest}")
            continue
        highest = sequence
        # The ID checks alone let a hand-resolved merge pass: a record pointing
        # at a same-numbered record from the other branch has a target that
        # exists and has the right kind. validate_record is what catches a
        # dangling or wrong-kind reference.
        try:
            checked = validate_record(record, prefix=prefix)
        except LedgerError as exc:
            faults.append(f"line {number}: {str(exc).removeprefix('docket: ')}")
        else:
            good.append(checked)
            prefix.add(checked)

    failed = bool(faults)
    if not faults:
        summary = f"{records} record{'s' if records != 1 else ''}"
        if correction_lines:
            summary += f" and {correction_lines} correction{'s' if correction_lines != 1 else ''}"
        print(f"docket: {path} reads cleanly, {summary}")
    else:
        print(f"docket: {path} has {len(faults)} fault{'s' if len(faults) != 1 else ''}")
        for fault in faults:
            print(f"  {fault}")
        print(
            "\nDuplicate or out-of-order IDs usually mean two branches recorded "
            "separately. Recover the other branch's ledger and run:"
        )
        print("  docket rebase OTHER_LEDGER")

    store = env.features_path()
    if store.exists():
        try:
            projected = feature_project.project(features.read(store))
        except features.FeatureError as exc:
            print(f"{store}: {str(exc).removeprefix('docket: ')}")
            failed = True
        else:
            print(f"{store}: ok")
            # seen, never a second env.read: read() raises on the first bad
            # line, so any ledger fault aborted the command that exists to
            # report every fault, and this check never ran. seen holds every id
            # the file carries, including one whose record failed
            # validate_record, so a reference to a repairable record is not
            # reported as dangling as well.
            for feature in projected:
                for field in ("include", "exclude"):
                    unknown = [ident for ident in feature[field] if ident not in seen]
                    if unknown:
                        print(f"{store}: {feature['id']} {field} names {', '.join(unknown)}")
                        failed = True

    for fault in feature_archive.faults(store):
        print(fault)
        failed = True

    return 1 if failed else 0


def cmd_init(args: argparse.Namespace) -> int:
    """Move this project's ledger into the repository so it can be committed."""
    root = env.project_root()
    target = root / env.LEDGER
    target.parent.mkdir(parents=True, exist_ok=True)
    ignore = target.parent / ".gitignore"
    if not ignore.exists():
        # The append lock is local state. A team that commits .docket/ would
        # otherwise commit it.
        ignore.write_text("*.lock\n", encoding="utf-8")
    if target.exists():
        print(f"docket: already project-local at {target}")
        return 0

    global_dir = env.global_root() / env.slug(root)
    existing = env.read(global_dir / "ledger.jsonl")
    with target.open("w") as f:
        for e in existing:
            f.write(json.dumps(e) + "\n")
    moved = (
        f", moved {len(existing)} entr{'y' if len(existing) == 1 else 'ies'}" if existing else ""
    )
    print(f"docket: created {target}{moved}")

    # features_path derives from the ledger's directory, so writing the ledger
    # above has already moved the feature store's location. Anything recorded
    # before this point is stranded in the global store, and the id counter
    # restarts at f1 against ids that still exist there.
    events = features.read(global_dir / "features.jsonl")
    if events:
        store = root / env.LEDGER.parent / "features.jsonl"
        with store.open("w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"docket: created {store}, moved {len(events)} feature event(s)")
    return 0


__all__ = ["cmd_check", "cmd_init", "cmd_migrate", "cmd_rebase"]
