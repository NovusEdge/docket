"""The proposal file, and what a human sees before accepting from it.

Construct stages here and stops. Acceptance is a separate step, because the
ledger records approvals and nothing else.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path

from docket.construct.schema import CONFIDENCE, STATES

PROPOSED = Path(".docket/proposed.jsonl")

# Reviewed in this order, so a reader meets the strongest records first.
_RANK = {name: index for index, name in enumerate(reversed(CONFIDENCE))}


class StageError(ValueError):
    """The staging file cannot be read as proposals."""


def read(path: Path) -> list[dict]:
    """Staged proposals, or nothing when the file does not exist yet.

    Marking proposals accepted means editing this file by hand, so a bad edit
    has to name the line rather than raise a decode error at whoever made it.
    """
    if not path.exists():
        return []
    items = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StageError(f"{path}: line {number} is not JSON: {exc}") from None
        if not isinstance(item, dict):
            raise StageError(f"{path}: line {number} is not an object")
        for field in ("key", "state", "kind"):
            if field not in item:
                raise StageError(f"{path}: line {number} has no {field!r}")
        if item["state"] not in STATES:
            raise StageError(f"{path}: line {number} has state {item['state']!r}; "
                             f"expected one of {', '.join(STATES)}")
        items.append(item)
    return items


def write(path: Path, proposals: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(p, ensure_ascii=False) for p in proposals)
    path.write_text(body + "\n" if body else "")


def merge(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """Fresh extraction, carrying forward what a human already decided.

    Keyed on the identity key, so the model's own wording can change between
    runs without losing an acceptance. A record whose anchor changed gets a new
    key and stages again, which is correct: the source text it was accepted
    against no longer exists.
    """
    decided = {p["key"]: p["state"] for p in existing if p["state"] != "staged"}
    merged = []
    for item in fresh:
        item = dict(item)
        item["state"] = decided.get(item["key"], "staged")
        merged.append(item)
    return merged


def resolves(proposal: dict, live: set[str]) -> bool:
    """Whether any scope entry addresses a file that still exists.

    A record whose scope matches nothing can never reach a briefing, so this
    decides review order. It never drops a record: a stale path can mean the
    record is dead, and it can equally mean the record is the only surviving
    account of a rename.
    """
    for item in proposal.get("scope") or []:
        for path in live:
            if path == item or fnmatch.fnmatchcase(path, item):
                return True
    return False


def resolution_rate(proposals: list[dict], live: set[str]) -> tuple[int, int]:
    """How many scoped records address live files, over how many are scoped.

    The acceptance signal for a whole run. A run resolving at 70% produces a
    ledger that mostly points at live code; one at 20% is building a museum,
    and the answer is to narrow the input set.
    """
    scoped = [p for p in proposals if p.get("scope")]
    return sum(1 for p in scoped if resolves(p, live)), len(scoped)


def review_groups(proposals: list[dict], live: set[str]) -> list[tuple[str, list[dict]]]:
    """Staged proposals by source document, strongest first within each.

    Nobody reads 520 proposals in order, so there is no linear reading order to
    preserve. Records whose scope resolves to nothing sink to the bottom of
    their group rather than disappearing.
    """
    groups: dict[str, list[dict]] = {}
    for item in proposals:
        if item.get("state") != "staged":
            continue
        groups.setdefault(item["source"]["path"], []).append(item)

    def order(item: dict) -> tuple[int, int]:
        return (0 if resolves(item, live) else 1,
                _RANK.get(item.get("confidence", "low"), len(CONFIDENCE)))

    return [(name, sorted(items, key=order)) for name, items in sorted(groups.items())]
