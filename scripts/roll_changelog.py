#!/usr/bin/env python3
"""Move the Unreleased section under a version heading, or refuse the release.

0.13.0 shipped with its entry still under `## [Unreleased]`, and nothing
reported it. `just release` calls this before it commits, so a release with no
changelog entry stops here instead of reaching a tag.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

UNRELEASED = "## [Unreleased]"
HEADING = re.compile(r"^## \[([^\]]+)\]", re.MULTILINE)
LINK = re.compile(r"^\[Unreleased\]:\s*(\S*?/compare/)(\S+?)\.\.\.HEAD\s*$", re.MULTILINE)


class ChangelogError(ValueError):
    """The changelog cannot carry this release as written."""


def _section(text: str) -> tuple[int, int, str]:
    """Where the Unreleased body starts and ends, and the body itself."""

    start = text.find(UNRELEASED)
    if start == -1:
        raise ChangelogError(f"no {UNRELEASED} heading")
    body_at = start + len(UNRELEASED)
    following = HEADING.search(text, body_at)
    end = following.start() if following else len(text)
    return body_at, end, text[body_at:end]


def roll(text: str, version: str, today: str) -> str:
    """Retitle the Unreleased body as ``version``, and leave a fresh Unreleased.

    The compare links at the foot move with it. Leaving them behind is
    invisible in review and produces a dead link on the released page.
    """

    if HEADING.search(text, 0) and f"## [{version}]" in text:
        raise ChangelogError(f"{version} already has a section")
    body_at, end, body = _section(text)
    if not body.strip():
        raise ChangelogError(f"{UNRELEASED} is empty; write the entry before releasing {version}")
    rolled = f"\n\n## [{version}] - {today}\n{body.rstrip()}\n\n"
    text = text[:body_at] + rolled + text[end:]

    match = LINK.search(text)
    if not match:
        raise ChangelogError("no [Unreleased] compare link to move")
    base, previous = match.group(1), match.group(2)
    text = (
        text[: match.start()]
        + (f"[Unreleased]: {base}v{version}...HEAD\n[{version}]: {base}{previous}...v{version}")
        + text[match.end() :]
    )
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="the release being cut, without a leading v")
    parser.add_argument("--date", required=True, metavar="YYYY-MM-DD")
    parser.add_argument("--path", type=Path, default=Path("CHANGELOG.md"))
    parser.add_argument(
        "--check", action="store_true", help="refuse an empty section, write nothing"
    )
    args = parser.parse_args(argv)

    text = args.path.read_text(encoding="utf-8")
    try:
        rolled = roll(text, args.version, args.date)
    except ChangelogError as exc:
        print(f"{args.path}: {exc}", file=sys.stderr)
        return 1
    if args.check:
        return 0
    args.path.write_text(rolled, encoding="utf-8")
    print(f"{args.path}: rolled Unreleased into {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
