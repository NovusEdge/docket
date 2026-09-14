"""The construct subcommand: stage proposals, review them, accept them.

Three steps, never one command. Extraction proposes, a human reads, acceptance
writes. Collapsing them would put records in the ledger nobody approved, and
approval is the whole thing the ledger records.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from docket import env

# docket.construct is imported inside the function bodies below, never here. A
# SessionStart hook builds this parser on every session, and it must not pay for
# a subpackage only this command uses.

MISSING_SDK = (
    "docket construct needs the openai SDK:\n"
    "    uv pip install openai        (or: python3 -m pip install --user openai)\n"
    "It is the only command that does. Every other command, and the "
    "SessionStart hook, run without it."
)

_WIDTH = 88
_TEXT_MAX = 400

# Every string in a proposal came from a model. Control characters would reach
# the terminal verbatim, and an escape sequence can repaint a reviewer's screen.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _safe(text: str, limit: int = _TEXT_MAX) -> str:
    """Model text fit to print: no control characters, bounded length."""
    clean = _CONTROL.sub("", str(text))
    return clean if len(clean) <= limit else clean[:limit] + "..."


def _docket_dir() -> Path:
    """The directory holding both the staging file and the ledger.

    A project's own .docket wins. Construct's main case is a project whose
    ledger does not exist yet, and there ledger_path() answers with the global
    store, which is nowhere the user would look for their own proposals. Pairing
    the two matters: proposals in one place and the records they became in
    another is worse than either choice alone.
    """
    local = env.project_root() / ".docket"
    if local.is_dir():
        return local
    return env.ledger_path().parent


def _staged_path() -> Path:
    return _docket_dir() / "proposed.jsonl"


def _ledger_path() -> Path:
    return _docket_dir() / env.LEDGER.name


def _live_paths() -> set[str]:
    """Every tracked path in the repository, for resolving a record's scope."""
    try:
        done = subprocess.run(["git", "ls-files", "-z"],
                              capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return set()
    if done.returncode != 0:
        return set()
    text = done.stdout.decode("utf-8", errors="surrogateescape")
    return {path for path in text.split("\0") if path}


def review(staged: Path, live: set[str]) -> int:
    """Print staged proposals grouped by source, strongest first.

    Each one carries its anchor, which is verbatim source text, so a reader can
    open the document and check the record against the line it came from.
    """
    from docket.construct import stage

    try:
        proposals = stage.read(staged)
    except stage.StageError as exc:
        print(f"docket: {exc}", file=sys.stderr)
        return 1
    groups = stage.review_groups(proposals, live)
    if not groups:
        print("docket: nothing staged for review")
        return 0

    resolved, scoped = stage.resolution_rate(
        [p for p in proposals if p.get("state") == "staged"], live)
    print(f"# scope resolves: {resolved}/{scoped}")
    print(f"# staged: {sum(len(items) for _, items in groups)}\n")

    for name, items in groups:
        print(f"## {_safe(name)}")
        for item in items:
            mark = "" if stage.resolves(item, live) else "  [unresolved scope]"
            print(f"  {item['kind']} ({item.get('confidence', 'low')}){mark}")
            for line in textwrap.wrap(_safe(item["text"]), width=_WIDTH):
                print(f"    {line}")
            if item.get("choice"):
                for line in textwrap.wrap(f"choice: {_safe(item['choice'])}",
                                          width=_WIDTH):
                    print(f"    {line}")
            if item.get("scope"):
                print(f"    scope: {_safe(', '.join(item['scope']))}")
            print(f"    anchor: {_safe(item['anchor'])}")
            print(f"    key: {item['key'][:12]}")
            print()
    return 0


def accept_staged(staged: Path, ledger: Path, source: str | None = None) -> int:
    """Append every accepted proposal through the ordinary ledger writer."""
    from docket.construct import accept

    written, skipped = accept.run(staged, ledger, source=source)
    if not written and not skipped:
        print("docket: nothing accepted yet; mark proposals accepted first")
        return 0
    print(f"docket: wrote {written} record{'' if written == 1 else 's'}")
    if skipped:
        print(f"docket: skipped {skipped}; a record whose support was not "
              "accepted would lose its grounds")
    return 0


def cmd_construct(args: argparse.Namespace) -> int:
    staged = _staged_path()

    if args.review and args.accept:
        print("docket: --review and --accept are separate steps", file=sys.stderr)
        return 2
    if args.paths and (args.review or args.accept):
        print("docket: extraction and review are separate steps; run construct "
              "with paths first, then --review", file=sys.stderr)
        return 2

    if args.review:
        return review(staged, _live_paths())
    if args.accept:
        return accept_staged(staged, _ledger_path(), source=args.source)
    if not args.paths:
        print("docket: name the documents to read, or pass --review or --accept",
              file=sys.stderr)
        return 2

    return _extract(args, staged)


def _extract(args: argparse.Namespace, staged: Path) -> int:
    """Run both passes and stage the result.

    The SDK import lives here, inside the one command body that needs it.
    """
    from docket.construct import run, stage

    # A dry run reads nothing and calls nothing, so it must not demand the
    # dependency. It is the one command someone runs to see what would happen.
    if not args.dry_run:
        try:
            import openai  # noqa: F401
        except ImportError:
            print(MISSING_SDK, file=sys.stderr)
            return 1

    exclude = () if args.no_exclude else run.EXCLUDE + tuple(args.exclude)

    try:
        proposals, report = run.two_pass(args.paths, jobs=args.jobs,
                                         dry_run=args.dry_run,
                                         exclude=exclude,
                                         untracked=args.untracked)
    except run.RunError as exc:
        print(f"docket: {exc}", file=sys.stderr)
        return 1

    for line in report:
        print(line)
    if args.dry_run:
        return 0

    merged = stage.merge(stage.read(staged), proposals)
    stage.write(staged, merged)
    print(f"docket: staged {len(merged)} proposals in {staged}")
    print("docket: read them with docket construct --review")
    return 0
