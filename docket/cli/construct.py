"""The construct subcommand: stage proposals, review them, accept them.

Three steps, never one command. Extraction proposes, a human reads, acceptance
writes. Collapsing them would put records in the ledger nobody approved, and
approval is the whole thing the ledger records.
"""

from __future__ import annotations

import argparse
import importlib
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from docket import env

# docket.construct is imported inside the function bodies below, never here. A
# SessionStart hook builds this parser on every session, and it must not pay for
# a subpackage only this command uses.


def missing_sdk(provider: str, package: str) -> str:
    """The install advice for the one SDK the chosen provider needs.

    The first form keeps the package in construct's own virtualenv, which is
    what the installer's construct step builds. The manual form names a
    virtualenv because Debian and Arch mark python3 EXTERNALLY-MANAGED, where
    pip refuses --user outright.
    """
    return (
        f"docket construct needs the {package} SDK for {provider}. Install it:\n"
        f"    docket construct --install-sdk {provider}\n"
        "That uses uv, so install uv first if it is missing. Otherwise install\n"
        f"{package} into a virtualenv yourself. Construct is the only command\n"
        "that needs an SDK; every other command, and the SessionStart hook, run\n"
        "without one."
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
        done = subprocess.run(["git", "ls-files", "-z"], capture_output=True, timeout=10)
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
        [p for p in proposals if p.get("state") == "staged"], live
    )
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
                for line in textwrap.wrap(f"choice: {_safe(item['choice'])}", width=_WIDTH):
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
        print(
            f"docket: skipped {skipped}; a record whose support was not "
            "accepted would lose its grounds"
        )
    return 0


def cmd_construct(args: argparse.Namespace) -> int:
    staged = _staged_path()

    # Both touch the SDK virtualenv and nothing else, so they run ahead of every
    # argument check below. The installer calls them.
    if args.install_sdk:
        return _install_sdk(args.install_sdk)
    if args.remove_sdk:
        from docket.construct import venv

        venv.remove()
        print(f"docket: removed {venv.root()}")
        return 0

    if args.review and args.accept:
        print("docket: --review and --accept are separate steps", file=sys.stderr)
        return 2
    if args.paths and (args.review or args.accept):
        print(
            "docket: extraction and review are separate steps; run construct "
            "with paths first, then --review",
            file=sys.stderr,
        )
        return 2

    if args.review:
        return review(staged, _live_paths())
    if args.accept:
        return accept_staged(staged, _ledger_path(), source=args.source)
    if not args.paths:
        print("docket: name the documents to read, or pass --review or --accept", file=sys.stderr)
        return 2

    return _extract(args, staged)


def _install_sdk(provider: str) -> int:
    """Put one provider's SDK in construct's virtualenv."""
    from docket.construct import client, venv

    spec = client.PROVIDERS.get(provider)
    if spec is None:
        print(
            f"docket: {provider!r} is not a provider; choose one of {', '.join(client.PROVIDERS)}",
            file=sys.stderr,
        )
        return 2

    print(f"docket: installing {spec['sdk']} into {venv.root()}")
    try:
        venv.install(spec["sdk"])
    except venv.VenvError as exc:
        print(f"docket: {exc}", file=sys.stderr)
        return 1
    print(f"docket: {provider} is ready")
    return 0


def _sdk_ready(package: str) -> bool:
    """Whether `package` imports, from this environment or construct's venv."""
    from docket.construct import venv

    try:
        importlib.import_module(package)
        return True
    except ImportError:
        pass
    if not venv.activate():
        return False
    try:
        importlib.import_module(package)
        return True
    except ImportError:
        return False


def _extract(args: argparse.Namespace, staged: Path) -> int:
    """Run both passes and stage the result.

    The SDK import lives here, inside the one command body that needs it.
    """
    from docket.construct import client, run, stage

    # A dry run reads nothing and calls nothing, so it must not demand the
    # dependency. It is the one command someone runs to see what would happen.
    if not args.dry_run:
        # Which SDK is missing depends on which key is set, so the key comes
        # first. Anthropic needs its own package; every other provider is
        # reached through openai.
        try:
            cfg = client.config()
        except client.ClientError as exc:
            print(f"docket: {exc}", file=sys.stderr)
            return 1
        if not _sdk_ready(cfg["sdk"]):
            # Nothing is installed here. Someone who skipped construct at setup
            # skipped it on purpose, and an agent runs this command with nobody
            # at the keyboard to answer a prompt.
            print(missing_sdk(cfg["provider"], cfg["sdk"]), file=sys.stderr)
            return 1

    exclude = () if args.no_exclude else run.EXCLUDE + tuple(args.exclude)

    try:
        proposals, report = run.two_pass(
            args.paths,
            jobs=args.jobs,
            dry_run=args.dry_run,
            exclude=exclude,
            untracked=args.untracked,
        )
    except (run.RunError, client.ClientError) as exc:
        # An absent key is the most ordinary way to reach this command. It
        # reached the user as a stack trace out of client.config().
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
