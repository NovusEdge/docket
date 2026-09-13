"""Locating a proposal in its source, and dating the document it came from.

Pass 1 runs a model over one document at a time. Everything in this module is
what happens locally around that call: proving the model quoted a real line,
and resolving a date the model is never asked for.
"""

from __future__ import annotations

import datetime as _datetime
import re
import subprocess
from pathlib import Path

from docket.construct.schema import normalize_anchor

# A date label in the document head, matched after the line is stripped of
# emphasis: the corpus writes both `Date:` and `**Date:**`, the second putting
# the colon inside the markers. The corpus carries no YAML front matter at all;
# 26 of its 372 documents open with a line like this instead.
_DATE_LINE = re.compile(r"^Date\s*:\s*(\d{4}-\d{2}-\d{2})")
_DATE_HEAD_LINES = 15

# Anywhere in the filename, not only the front. positioning-2026-05-24.md
# carries its date mid-name, where a leading-date parse finds nothing.
_DATE_NAME = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def anchor_line(anchor: str, source: str) -> int | None:
    """The 1-based line the anchor quotes, or None.

    Compares normalized whole lines. A model asked for a verbatim line returns
    the words and drops the emphasis around them, so `**Decision:** Option B`
    in the source arrives as `Decision: Option B`. Matching raw strings cost
    the spike a third of its batch-one anchors.

    Whole lines, never substrings: a three-word anchor matched as a substring
    would claim any paragraph containing those words.
    """
    wanted = normalize_anchor(anchor)
    if not wanted:
        return None
    for number, line in enumerate(source.splitlines(), start=1):
        if normalize_anchor(line) == wanted:
            return number
    return None


def match_rate(proposals: list[dict], source: str) -> tuple[int, int]:
    """How many proposals quote a real line, over how many there are.

    The quality signal for one document's extraction. A run whose anchors stop
    matching means the model started paraphrasing, and every record from it
    needs a human before it is trusted.
    """
    matched = sum(1 for p in proposals if anchor_line(p.get("anchor", ""), source))
    return matched, len(proposals)


def date_from_text(text: str) -> str | None:
    """A date the document states about itself, or None.

    Only the head counts. A date further down is a fact about the subject,
    never about the document.
    """
    for line in text.splitlines()[:_DATE_HEAD_LINES]:
        found = _DATE_LINE.match(normalize_anchor(line))
        if found:
            return found.group(1)
    return None


def date_from_name(name: str) -> str | None:
    """A real calendar date in the filename, or None."""
    found = _DATE_NAME.search(name)
    if not found:
        return None
    year, month, day = (int(part) for part in found.groups())
    try:
        return _datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def git_dates(root: Path) -> dict[str, str]:
    """Every tracked path under root, mapped to its last commit date.

    One call for the whole tree. 133 of the 372 documents in the corpus this
    was built against carry no date in their name or their head, so a
    subprocess per file would make dating the slowest part of a run.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "log", "--name-only", "--date=short",
             "--format=%x00%ad", "--no-renames"],
            capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return {}
    if done.returncode != 0:
        return {}

    dates: dict[str, str] = {}
    current = ""
    # Newest commit first, so the first date a path appears under is its last.
    for line in done.stdout.decode("utf-8", errors="surrogateescape").splitlines():
        if line.startswith("\0"):
            current = line[1:].strip()
        elif line.strip() and current:
            dates.setdefault(line.strip(), current)
    return dates


def resolve_date(name: str, text: str, git: dict[str, str]) -> str | None:
    """The document's date, by the most specific source that has one.

    What the document says about itself beats what its name says, which beats
    what git remembers. A document with no date from any source resolves to
    None, and pass 2 proposes no supersession edge for its records.
    """
    return date_from_text(text) or date_from_name(Path(name).name) or git.get(name)
