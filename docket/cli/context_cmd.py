"""docket context: the briefing a harness injects at session start.

Split from docket.cli.query to keep that file under the 300 line limit. list,
show and where print records a person asked for. This one assembles a whole
briefing under a character budget, and it runs on every session start.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

from docket import ROOT, env, version
from docket.cli.autoscope import auto_scope_files
from docket.context_model import positions
from docket.env import read
from docket.ledger import LedgerError, project

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


def _print_context(text: str, args: argparse.Namespace, notice: str | None = None) -> int:
    body = f"{notice}\n{text}" if notice else text
    if not body:
        return 0
    if args.for_harness:
        print(json.dumps(CONTEXT_ENVELOPES[args.for_harness](body)))
    else:
        print(body, end="")
    return 0


def _feature_block(root, entries=None) -> str:
    """The active feature's brief, or an empty string when nothing applies.

    This runs on every session start through the hook. A repository with no
    feature store, no git, or a store that will not read must still get a
    briefing, so every failure here degrades to no header.

    ``entries`` takes the projected ledger the caller already holds. Reading
    and projecting it again here doubled that work on every session start.
    """
    from docket import config, feature_brief, feature_project, features

    try:
        path = env.features_path()
        if not path.exists():
            return ""
        current = feature_project.project(features.read(path))
        branch = env.branch(root)
        open_now = [f for f in current if f["state"] not in features.TERMINAL_STATES]
        on_branch = [f for f in open_now if f["branch"] == branch] if branch else []
        candidates = on_branch or open_now
        if not candidates:
            return ""
        feature = candidates[-1]
        if entries is None:
            entries = project(read(env.ledger_path()), validated=True)
        files = feature_brief.expand(root, feature["paths"])
        attached = feature_brief.attach(
            entries, files, include=feature["include"], exclude=feature["exclude"]
        )
        blockers = feature_brief.blocking(attached)
        if blockers:
            feature = dict(feature, state="blocked")
        # The spec caps the header at the feature plus its three highest-ranked
        # records. The character share alone let a briefing with short records
        # carry a dozen, which is the record selection's job, not the header's.
        settings, _ = config.load(path.parent)
        return feature_brief.render(
            feature,
            attached[:3],
            limit_chars=feature_brief.budget_share(settings),
        )
    # SubprocessError covers TimeoutExpired, which git ls-files raises on a
    # slow or huge tree. It is not an OSError, so it escaped and turned a
    # session start into a traceback.
    except (features.FeatureError, LedgerError, OSError, subprocess.SubprocessError):
        return ""


def cmd_context(args: argparse.Namespace) -> int:
    from docket.config import ConfigError
    from docket.config import load as load_settings
    from docket.context import build_context as render_context

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
        at = positions(raw)
        # An unknown baseline yields an empty prefix, and build_delta then
        # returns None on the same id. Do not raise here.
        prefix = raw[: at[ident] + 1] if ident in at else []
        projected = project(raw)
        delta = build_delta(
            projected,
            since=args.since,
            baseline=project(prefix),
            raw=raw,
            max_chars=args.max_chars,
            ledger=str(env.ledger_path()),
            settings=settings,
        )
        if delta is not None:
            # A delta briefing is the resumed-session case the feature store
            # exists for, so it carries the header the full briefing carries.
            block = _feature_block(env.project_root(), projected)
            return _print_context(f"{block}\n\n{delta}" if block else delta, args, line)
        print(
            f"docket: baseline {args.since} is unknown or stale; printing a full briefing",
            file=sys.stderr,
        )

    files = tuple(args.file or ())
    forced = args.auto_scope is True
    default_on = args.auto_scope is None and not args.query and not files and not args.all_records
    if forced or default_on:
        files = tuple(dict.fromkeys(files + auto_scope_files(settings["auto_scope"]["limit"])))
    try:
        raw = read(env.ledger_path())
        entries = project(raw, validated=True)
        text = render_context(
            entries,
            query=args.query or "",
            files=files,
            max_chars=args.max_chars,
            ledger=str(env.ledger_path()),
            all_records=args.all_records,
            settings=settings,
            settings_id=settings_id,
            feature=_feature_block(env.project_root(), entries),
            latest_id=raw[-1]["id"] if raw else "",
        )
    except (LedgerError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return _print_context(text, args, line)


__all__ = ["CONTEXT_ENVELOPES", "cmd_context", "update_line"]
