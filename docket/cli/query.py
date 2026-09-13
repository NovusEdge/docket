"""Commands that read the ledger: list, show, where, context."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
import time

from docket import ROOT, version
from docket.cli.term import _DIM, _STATE_COLOR, _c, _match, _use_color
from docket import env
from docket.env import LEDGER, justification_sets, read, retired_by
from docket.ledger import ID_RE, LedgerError, project

_LIST_ID_W, _LIST_STATE_W = 5, 9
_LIST_HEAD_W = _LIST_ID_W + 1 + _LIST_STATE_W + 1  # clears the id+state columns


def _list_dim_tail(line: str, marker: str, use_color: bool) -> str:
    """Dim a line from `marker` onward, if the line carries it at all.

    Wrapping can split the marker onto a line of its own or leave it whole;
    either way the dim colour must start where the marker starts, not at
    column 0.
    """
    idx = line.find(marker)
    if idx == -1 or not use_color:
        return line
    return line[:idx] + _c(_DIM, line[idx:], use_color)


def cmd_list(args: argparse.Namespace) -> int:
    entries = project(read(env.ledger_path()), validated=True)
    retired = retired_by(entries)
    if not args.superseded:
        entries = [e for e in entries if e.get("id") not in retired]
    if args.state:
        entries = [e for e in entries if e.get("state") == args.state]
    if getattr(args, "kind", None):
        entries = [e for e in entries if e.get("kind") == args.kind]
    if args.find:
        entries = [e for e in entries if _match(e, args.find)]
    if not entries:
        if getattr(args, "json", False):
            print("[]")
            return 0
        print("docket: nothing recorded")
        return 0
    if getattr(args, "json", False):
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0

    use_color = False if args.plain else True if args.pretty else _use_color()
    width = shutil.get_terminal_size().columns

    if args.oneline:
        for e in entries:
            id_str = _c(_STATE_COLOR.get(e["state"], _DIM), f"{e['id']:<{_LIST_ID_W}}", use_color)
            # Truncated, never wrapped: one entry stays one line, which is what
            # makes the mode scannable and pipeable into grep.
            room = max(width - _LIST_ID_W - _LIST_STATE_W - 2, 20)
            question = textwrap.shorten(e["text"], width=room, placeholder="...")
            print(f"{id_str} {e['state']:<{_LIST_STATE_W}} {question}")
        return 0

    for e in entries:
        sets = justification_sets(e)
        # " | " separates alternatives; each alternative's own ids stay comma-joined.
        dep = f"  <- {' | '.join(','.join(s) for s in sets)}" if sets else ""
        gone = f"  (superseded by {retired[e['id']]})" if e.get("id") in retired else ""

        id_str = _c(_STATE_COLOR.get(e["state"], _DIM), f"{e['id']:<{_LIST_ID_W}}", use_color)
        state_str = _c(_STATE_COLOR.get(e["state"], _DIM), f"{e['state']:<{_LIST_STATE_W}}", use_color)

        avail = max(width - _LIST_HEAD_W, 20)
        wrapped = textwrap.wrap(e["text"] + dep + gone, width=avail) or [""]
        print(f"{id_str} {state_str} " + _list_dim_tail(_list_dim_tail(wrapped[0], "<-", use_color), "(superseded by", use_color))
        for line in wrapped[1:]:
            line = _list_dim_tail(_list_dim_tail(line, "<-", use_color), "(superseded by", use_color)
            print(" " * _LIST_HEAD_W + line)

        detail = e.get("choice", e.get("rationale", ""))
        if detail:
            for line in textwrap.wrap(detail, width=max(width - 6, 20)) or [""]:
                print("      " + line)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    raw = read(env.ledger_path())
    if args.at:
        if not any(item.get("id") == args.at for item in raw):
            print(f"docket: unknown record {args.at}", file=sys.stderr)
            return 1
        cutoff = int(args.at[1:])
        raw = [item for item in raw if int(item["id"][1:]) <= cutoff]
    entries = project(raw, validated=True)
    by_id = {e.get("id"): e for e in entries}
    e = by_id.get(args.id)
    if not e:
        print(f"docket: no entry {args.id}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(e, indent=2))
        return 0

    def cite(i: str) -> str:
        q = by_id.get(i, {}).get("text")
        return f"{i} ({q})" if q else i

    width = shutil.get_terminal_size().columns

    def field(label: str, value: str) -> None:
        """One labelled field, wrapped under a hanging indent past the label."""
        indent = " " * (len(label) + 4)
        for i, line in enumerate(textwrap.wrap(f"  {label}: {value}", width=width,
                                               subsequent_indent=indent) or [f"  {label}:"]):
            print(line)

    for line in textwrap.wrap(f"{e['id']}  {e.get('kind', '')}  {e.get('state', '')}  {e.get('text', '')}",
                              width=width, subsequent_indent=" " * 15):
        print(line)
    field("Choice", e.get("choice", ""))
    field("Rationale", e.get("rationale", ""))
    sets = justification_sets(e)
    if sets:
        field("Because", " | ".join(", ".join(cite(i) for i in s) for s in sets))
    supersedes = e.get("supersedes") or []
    if supersedes:
        field("Supersedes", ", ".join(cite(i) for i in supersedes))
    retired = retired_by(entries)
    if e["id"] in retired:
        field("Superseded by", cite(retired[e["id"]]))
    if e.get("depends_on"):
        field("Depends on", ", ".join(cite(i) for i in e["depends_on"]))
    if e.get("answers"):
        field("Answers", ", ".join(cite(i) for i in e["answers"]))
    if e.get("resolved_by"):
        field("Resolved by", ", ".join(cite(i) for i in e["resolved_by"]))
    if e.get("decided_by"):
        field("Decided by", e["decided_by"])
    if e.get("cost_if_wrong"):
        field("Cost if wrong", e["cost_if_wrong"])
    field("Recorded state", e.get("recorded_state", e.get("state", "")))
    print(f"  Author: {e.get('author', '')}  Session: {e.get('session', '')}  Branch: {e.get('branch', '')}")
    return 0


def cmd_where(args: argparse.Namespace) -> int:
    path = env.ledger_path()
    kind = "project" if LEDGER.name in str(path) and ".claude" not in str(path) else "global"
    print(f"{path}  ({kind}, {'exists' if path.exists() else 'not created yet'})")
    return 0


# Harnesses that want context as their own hook envelope instead of plain
# text, keyed by the --for value. docs/installation.md is the source for
# these shapes; codex is absent because no local hooks.json on this machine
# shows what it expects, and guessing would ship a shape nobody verified.
CONTEXT_ENVELOPES = {
    "gemini": lambda text: {
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
    },
    "copilot": lambda text: {"additionalContext": text},
    "cursor": lambda text: {"additional_context": text},
}


_AUTO_SCOPE_LIMIT = 50


def auto_scope_files(limit: int = _AUTO_SCOPE_LIMIT) -> tuple[str, ...]:
    """Changed and untracked paths, as the working tree's proxy for a task.

    Both commands run from the repository root. git ls-files lists only what
    sits under the current directory, and git diff prints root-relative paths,
    so running from a subdirectory would drop files and mix two path bases.
    -z output, because a path may contain a newline.
    """

    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return ()
    if top.returncode != 0:
        return ()
    root = top.stdout.strip()

    groups: list[list[str]] = []
    for command in (
        ["git", "diff", "--name-only", "-z", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
    ):
        try:
            # Bytes, not text: the locale codec decodes strictly, and a path
            # carrying an invalid byte would raise UnicodeDecodeError, which is
            # neither OSError nor SubprocessError and would kill every
            # docket context in that repository.
            done = subprocess.run(command, cwd=root, capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            return ()
        # A repository with no commits has no HEAD, so the diff fails while
        # ls-files still reports every untracked file. Skip the failed command
        # and keep what the other one found.
        if done.returncode != 0:
            groups.append([])
            continue
        text = done.stdout.decode("utf-8", errors="surrogateescape")
        # git collapses an untracked nested repository to a directory entry
        # with a trailing slash. A scope matches files, so such an entry can
        # never match and would spend a slot in the cap.
        groups.append([path for path in text.split("\0")
                       if path and not path.endswith("/")])

    # Interleave the two sources. Taking the head of a concatenated list let a
    # branch with more than `limit` modified files starve every untracked one,
    # which is the work in progress.
    paths: list[str] = []
    for index in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if index < len(group) and group[index] not in paths:
                paths.append(group[index])

    if not paths:
        # A clean tree says nothing about the task. The last commit does, and it
        # is the likeliest starting point for the next piece of work. --root
        # keeps a first commit readable, and -m keeps a merge readable, because
        # a combined diff prints nothing for either.
        try:
            done = subprocess.run(
                ["git", "diff-tree", "-m", "--root", "--no-commit-id",
                 "--name-only", "-r", "-z", "HEAD"],
                cwd=root, capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            return ()
        # A repository with no commits has no HEAD, so git exits non-zero and
        # the briefing stays unscoped.
        if done.returncode == 0:
            text = done.stdout.decode("utf-8", errors="surrogateescape")
            # -m prints one diff per parent, so a merge repeats a path.
            paths = list(dict.fromkeys(
                path for path in text.split("\0") if path and not path.endswith("/")))
    return tuple(paths[:limit])


def update_line() -> str | None:
    """One notice line, or None. Never performs a network request."""
    from docket.update import disabled, due, notice, read_state, spawn_fetch

    try:
        if disabled():
            return None
        # ROOT, never __file__: this module sits two levels below the checkout,
        # so parent.parent would name docket/ and the refresh would respawn
        # this file instead of the CLI.
        state = read_state()
        if due(state, time.time()):
            spawn_fetch(ROOT / "bin" / "docket")
        return notice(version(), str(state.get("latest", "")), ROOT)
    except Exception:
        return None


def _print_context(text: str, args: argparse.Namespace,
                   notice: str | None = None) -> int:
    body = f"{notice}\n{text}" if notice else text
    if not body:
        return 0
    if args.for_harness:
        print(json.dumps(CONTEXT_ENVELOPES[args.for_harness](body)))
    else:
        print(body, end="")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    from docket.context import build_context as render_context
    from docket.config import ConfigError, load as load_settings
    try:
        settings, settings_id = load_settings(env.ledger_path().parent)
    except ConfigError as exc:
        print(f"docket: {exc}", file=sys.stderr)
        return 1
    line = update_line()
    # Validate against the loaded minimum, not a literal. A config that raises
    # budget.minimum would otherwise let a too-small value through and surface
    # as an uncaught ValueError from the renderer.
    minimum = settings["budget"]["minimum"]
    if args.max_chars is not None and args.max_chars < minimum:
        print(f"docket: --max-chars must be at least {minimum}", file=sys.stderr)
        return 2
    if args.since:
        from docket.context import build_delta
        try:
            raw = read(env.ledger_path())
        except (LedgerError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        # Project twice. The second projection is the history as it stood at the
        # baseline, and the renderer needs it to tell a new loss from an old one.
        ident = args.since.partition("@")[0]
        cutoff = int(ident[1:]) if ID_RE.fullmatch(ident) else -1
        prefix = [item for item in raw if int(item["id"][1:]) <= cutoff]
        delta = build_delta(project(raw), since=args.since,
                            baseline=project(prefix),
                            max_chars=args.max_chars, ledger=str(env.ledger_path()),
                            settings=settings)
        if delta is not None:
            return _print_context(delta, args, line)
        print(f"docket: baseline {args.since} is unknown or stale; "
              "printing a full briefing", file=sys.stderr)

    files = tuple(args.file or ())
    forced = args.auto_scope is True
    default_on = (args.auto_scope is None and not args.query
                  and not files and not args.all_records)
    if forced or default_on:
        files = tuple(dict.fromkeys(files + auto_scope_files(settings["auto_scope"]["limit"])))
    try:
        text = render_context(
            project(read(env.ledger_path()), validated=True),
            query=args.query or "",
            files=files,
            max_chars=args.max_chars,
            ledger=str(env.ledger_path()),
            all_records=args.all_records,
            settings=settings,
            settings_id=settings_id,
        )
    except (LedgerError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return _print_context(text, args, line)
