from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from docket import ROOT, env, version
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
    count = 0
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            faults.append(f"line {number}: invalid JSON: {exc.msg}")
            continue
        count += 1
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

    if not faults:
        print(f"docket: {path} reads cleanly, {count} record{'s' if count != 1 else ''}")
        return 0
    print(f"docket: {path} has {len(faults)} fault{'s' if len(faults) != 1 else ''}")
    for fault in faults:
        print(f"  {fault}")
    print(
        "\nDuplicate or out-of-order IDs usually mean two branches recorded "
        "separately. Recover the other branch's ledger and run:"
    )
    print("  docket rebase OTHER_LEDGER")
    return 1


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

    existing = env.read(env.global_root() / env.slug(root) / "ledger.jsonl")
    with target.open("w") as f:
        for e in existing:
            f.write(json.dumps(e) + "\n")
    moved = (
        f", moved {len(existing)} entr{'y' if len(existing) == 1 else 'ies'}" if existing else ""
    )
    print(f"docket: created {target}{moved}")
    return 0


_COMPLETION_FLAGS = (
    "--state",
    "--choice",
    "--alternative",
    "--scope",
    "--rationale",
    "--supports",
    "--depends-on",
    "--answers",
    "--supersedes",
    "--evidence",
    "--revisit",
    "--cost",
    "--pin",
    "--kind",
    "--query",
    "--file",
    "--max-chars",
    "--auto-scope",
    "--no-auto-scope",
    "--since",
    "--at",
    "--all",
    "--find",
    "--superseded",
    "--oneline",
    "--json",
    "--plain",
    "--pretty",
    "--style",
    "--interactive",
    "--no-interactive",
    "--for",
    "--version",
    "--dry-run",
    "--check",
)
_COMPLETION_CMDS = (
    "claim",
    "decision",
    "question",
    "list",
    "show",
    "graph",
    "context",
    "where",
    "check",
    "rebase",
    "migrate",
    "init",
    "completion",
    "update",
)

_BASH_COMPLETION = f"""\
_docket() {{
    local cur prev
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    case "$prev" in
        --state) COMPREPLY=($(compgen -W "unassessed accepted disputed rejected adopted revoked open resolved" -- "$cur")); return ;;
        --supports|--depends-on|--answers|--supersedes|show)
            COMPREPLY=($(compgen -W "$(docket list --oneline 2>/dev/null | awk '{{print $1}}')" -- "$cur")); return ;;
        completion) COMPREPLY=($(compgen -W "bash zsh fish" -- "$cur")); return ;;
    esac
    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "{" ".join(_COMPLETION_FLAGS)}" -- "$cur")); return
    fi
    COMPREPLY=($(compgen -W "{" ".join(_COMPLETION_CMDS)}" -- "$cur"))
}}
complete -F _docket docket
"""

_ZSH_COMPLETION = f"""\
#compdef docket

_docket_ids() {{
    local -a ids
    ids=(${{(f)"$(docket list --oneline 2>/dev/null | awk '{{print $1}}')"}})
    _describe 'id' ids
}}

_arguments -C \\
    '1: :({" ".join(_COMPLETION_CMDS)})' \\
    '*::arg:->args'

case $words[1] in
    show) _docket_ids ;;
    completion) _values 'shell' bash zsh fish ;;
    claim|decision|question)
        _arguments \\
            '--state[state]:state:(unassessed accepted disputed rejected adopted revoked open resolved)' \\
            '--choice[decision choice]:choice:' \\
            '--alternative[decision alternative]:alternative:' \\
            '--supports[supporting ids]:id:_docket_ids' \\
            '--depends-on[decision prerequisites]:id:_docket_ids' \\
            '--answers[question ids]:id:_docket_ids' \\
            '--supersedes[retired ids]:id:_docket_ids' \\
            '--cost[cost if wrong]:cost:'
        ;;
esac
"""

_FISH_COMPLETION = f"""\
set -l docket_cmds {" ".join(_COMPLETION_CMDS)}
complete -c docket -n "not __fish_seen_subcommand_from $docket_cmds" -a "$docket_cmds"
complete -c docket -n "__fish_seen_subcommand_from show" -a "(docket list --oneline 2>/dev/null | awk '{{print \\$1}}')"
complete -c docket -n "__fish_seen_subcommand_from claim decision question" -l supports -a "(docket list --oneline 2>/dev/null | awk '{{print \\$1}}')"
complete -c docket -n "__fish_seen_subcommand_from claim decision question" -l supersedes -a "(docket list --oneline 2>/dev/null | awk '{{print \\$1}}')"
complete -c docket -n "__fish_seen_subcommand_from claim decision" -l state -a "unassessed accepted disputed rejected adopted revoked"
complete -c docket -n "__fish_seen_subcommand_from completion" -a "bash zsh fish"
"""

_COMPLETIONS = {"bash": _BASH_COMPLETION, "zsh": _ZSH_COMPLETION, "fish": _FISH_COMPLETION}


def cmd_completion(args: argparse.Namespace) -> int:
    print(_COMPLETIONS[args.shell], end="")
    return 0


LAUNCHER_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/NovusEdge/docket/refs/tags/{tag}/installer/install.py"
)
MAIN_LAUNCHER_URL = "https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py"


def cmd_update(args: argparse.Namespace, root: Path | None = None) -> int:
    from docket.update import is_newer, parse_version, read_state, shape, update_command

    # ROOT, never __file__: this module sits two levels below the checkout, so
    # parent.parent would name docket/ and update_command would print a path
    # that does not exist.
    root = root or ROOT
    running = version()
    latest = str(read_state().get("latest", ""))
    if args.check:
        if not latest or parse_version(latest) is None:
            print("docket: no cached release information yet")
            return 2
        if is_newer(latest, running):
            print(f"docket {latest.lstrip('v')} is available (running {running})")
            return 1
        print(f"docket {running} is up to date")
        return 0

    kind = shape(root)
    if kind == "plugin":
        print(f"docket: this copy is managed by your harness. Run: {update_command(root)}")
        return 0
    if kind == "unknown":
        print(f"docket: this copy has no installer and no repository. Run: {update_command(root)}")
        return 0
    if kind == "source":
        command = [
            sys.executable,
            str(root / "installer" / "install.py"),
            "--checkout",
            str(root),
            "--update",
        ]
        print(" ".join(command))
        return subprocess.call(command)
    tag = latest if latest and parse_version(latest) is not None else None
    return _run_downloaded_update(tag, root)


def _managed_prefix(root: Path) -> str:
    """The command directory this checkout was installed under, or "".

    The installer writes the prefix into .docket-managed, and --update
    validates the installed command against the checkout it pairs with. The
    downloaded launcher runs outside the checkout and cannot find either one
    on its own, so both travel as arguments.
    """
    try:
        marker = json.loads((root / ".docket-managed").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    prefix = marker.get("prefix") if isinstance(marker, dict) else None
    return prefix if isinstance(prefix, str) else ""


def _run_downloaded_update(tag: str | None, root: Path) -> int:
    """Fetch the launcher and run it outside the checkout.

    The bundled launcher takes its own checkout branch, which needs Go and
    passes --checkout, and --checkout makes the planner skip the git update.
    Without a cached release tag, fall back to the main branch so a fresh
    install (no cache populated yet) can still update.
    """
    from urllib.request import urlopen

    url = LAUNCHER_URL_TEMPLATE.format(tag=tag) if tag else MAIN_LAUNCHER_URL
    with tempfile.TemporaryDirectory() as work:
        launcher = Path(work) / "install.py"
        try:
            with urlopen(url, timeout=30) as response:
                launcher.write_bytes(response.read())
        except OSError as exc:
            print(f"docket: could not download the installer: {exc}", file=sys.stderr)
            return 1
        command = [sys.executable, str(launcher), "--update", "--dir", str(root)]
        if prefix := _managed_prefix(root):
            command += ["--prefix", prefix]
        print(" ".join(command))
        return subprocess.call(command, cwd=work)


def cmd_update_fetch(args: argparse.Namespace) -> int:
    from docket.update import run_fetch

    return run_fetch(time.time())
