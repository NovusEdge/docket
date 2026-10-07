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

from docket import env, feature_archive, feature_project, features, merge_setup
from docket.cli.context_cmd import migrate_instruction
from docket.ledger import (
    ID_RE,
    LedgerError,
    SchemaTooOld,
    _ledger_lock,
    _Prefix,
    append,
    rebind,
    stale_keys,
    validate_record,
)


def cmd_rebase(args: argparse.Namespace) -> int:
    """Append another branch's divergent tail under fresh IDs."""
    from docket.rebase import RebaseError, renumber

    path = env.ledger_path()
    other = Path(args.other)
    if not other.is_file():
        print(f"docket: no ledger at {other}", file=sys.stderr)
        return 1
    try:
        mine = env.read(path, strict=True)
        theirs = env.read(other, strict=True)
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


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def cmd_migrate(args: argparse.Namespace) -> int:
    """Convert this project's ledger to the current schema."""
    from docket.migrate import (
        SCHEMA_LATEST,
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
    version = None
    try:
        version = detect_version(read_source(path))
        if args.emit_map:
            if version == SCHEMA_LATEST:
                print(f"docket: already schema {SCHEMA_LATEST}")
                return 0
            if version != 1:
                raise MigrationError(
                    f"--emit-map applies to a schema 1 ledger; this one is at schema {version}, "
                    "whose records are already typed"
                )
            mapping = derive_mapping(read_source(path))
            Path(args.emit_map).write_text(
                json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(
                f"docket: wrote {len(mapping)} mapping entr"
                f"{'y' if len(mapping) == 1 else 'ies'} to {args.emit_map}"
            )
            return 0
        result = migrate_in_place(
            path, mapping_path=args.map, dry_run=args.dry_run, rewrite=args.rewrite
        )
    except MigrationError as exc:
        print(f"docket: {exc}", file=sys.stderr)
        if version == 1:
            print(
                "docket: to classify records by hand, run 'docket migrate --emit-map FILE', "
                "edit FILE, then 'docket migrate --map FILE'",
                file=sys.stderr,
            )
        return 2
    except OSError as exc:
        print(f"docket: {exc}", file=sys.stderr)
        return 1
    if not result.count:
        # A current ledger whose features files were not.
        extra = (
            f"; remapped {_count(result.features_events, 'features event')}"
            if result.features_events
            else ""
        )
        print(f"docket: already schema {SCHEMA_LATEST}{extra}")
        return 0
    for note in result.notes:
        print(f"docket: warning: {note}", file=sys.stderr)
    dry = args.dry_run
    if dry:
        for line in result.report:
            print(line)
        for change in result.prose_changes:
            if change.after is None:
                print(f"  {change.line_id} {change.field}: unmapped {change.before}")
            else:
                print(f"  {change.line_id} {change.field}: {change.before} -> {change.after}")
    kinds = ", ".join(
        _count(result.per_kind.get(kind, 0), kind) for kind in ("claim", "decision", "question")
    )
    print(
        f"docket: {'would migrate' if dry else 'migrated'} {_count(result.count, 'record')} "
        f"from schema {version} to schema {SCHEMA_LATEST} ({kinds})"
    )
    rewritten = sum(1 for change in result.prose_changes if change.after is not None)
    unmapped = len(result.prose_changes) - rewritten
    done = "would rewrite" if dry else "rewrote"
    parts = [_count(rewritten, "prose field")]
    if result.features_events:
        parts.append(_count(result.features_events, "features event"))
    print(f"docket: {done} {' and '.join(parts)}")
    if unmapped:
        print(f"docket: left {_count(unmapped, 'unmapped id')} as written")
    if result.rewritten:
        total = sum(result.rewrite_counts.values())
        print(
            f"docket: {done} {_count(total, 'id mention')} in "
            f"{_count(len(result.rewritten), 'file')}"
        )
        for name in result.rewritten:
            if dry:
                print(f"  {name}: {_count(result.rewrite_counts[name], 'id')}")
            else:
                print(f"  {name}")
    if not dry:
        print(f"docket: original kept at {path}.schema{version}")
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
    highest: dict[str, int] = {}
    records = 0
    correction_lines = 0
    review_lines = 0
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            faults.append(f"line {number}: invalid JSON: {exc.msg}")
            continue
        if isinstance(record, dict) and record.get("kind") in ("correction", "review"):
            if record["kind"] == "review":
                review_lines += 1
            else:
                correction_lines += 1
            # Kept out of seen: a feature that names a correction id names
            # nothing a brief can attach, and the feature check reports it.
            try:
                checked = validate_record(record, prefix=prefix)
            except SchemaTooOld as exc:
                print(migrate_instruction(exc), end="")
                return 1
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
        letter = match.group(1)
        past = highest.get(letter, 0)
        sequence = int(match.group(2))
        if sequence <= past:
            faults.append(f"line {number}: id {ident} does not increase past {letter}{past}")
            continue
        highest[letter] = sequence
        # The ID checks alone let a hand-resolved merge pass: a record pointing
        # at a same-numbered record from the other branch has a target that
        # exists and has the right kind. validate_record is what catches a
        # dangling or wrong-kind reference.
        try:
            checked = validate_record(record, prefix=prefix)
        except SchemaTooOld as exc:
            print(migrate_instruction(exc), end="")
            return 1
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
        if review_lines:
            summary += f" and {review_lines} review{'s' if review_lines != 1 else ''}"
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
                    rebound = rebind(feature[field], feature["keys"], good)
                    moved = [f"{a} -> {b}" for a, b in zip(feature[field], rebound) if a != b]
                    if moved:
                        print(
                            f"{store}: {feature['id']} {field} names records a merge "
                            f"renumbered ({', '.join(moved)}); run docket feature remap"
                        )
                        failed = True
                    stale = (
                        []
                        if feature["state"] in features.TERMINAL_STATES
                        else stale_keys(feature[field], feature["keys"], good)
                    )
                    if stale:
                        print(
                            f"{store}: {feature['id']} {field} names {', '.join(stale)}, "
                            "whose stored key matches no record; check which record was "
                            "meant and re-cite it with docket feature amend"
                        )
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
    for message in merge_setup.setup(root):
        print(message)
    if target.exists():
        print(f"docket: already project-local at {target}")
        return 0

    global_dir = env.global_root() / env.slug(root)
    source = global_dir / "ledger.jsonl"
    # Held across the copy so an append to the global ledger cannot land
    # between the read and the moment ledger_path starts resolving to target.
    with _ledger_lock(source):
        existing = env.read(source, lock=False, strict=True)
        feature_archive.write_lines(target, existing)
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
        feature_archive.write_lines(store, events)
        print(f"docket: created {store}, moved {len(events)} feature event(s)")
    return 0


def cmd_merge_driver(args: argparse.Namespace) -> int:
    """Git merge driver entry point; see docket/merge_driver.py."""
    from docket import merge_driver

    return merge_driver.run(Path(args.base), Path(args.ours), Path(args.theirs))


__all__ = ["cmd_check", "cmd_init", "cmd_merge_driver", "cmd_migrate", "cmd_rebase"]
