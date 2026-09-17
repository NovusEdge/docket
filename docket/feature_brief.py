"""Which ledger records govern a feature's declared paths.

Nothing is linked by hand. A feature declares paths, those paths expand
against the tracked tree, and every ledger record whose scope covers one of
those files attaches.
"""

from __future__ import annotations

import fnmatch
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from docket.config import DEFAULTS
from docket.context import scope_strength

_WILDCARDS = "*?["


def specificity(scope: str) -> int:
    """Length of the literal prefix before the first wildcard.

    gitignore resolves competing patterns by taking the most specific one.
    The same rule breaks the ties scope_strength leaves: it returns max() over
    the file set, one integer with no match count and no decay, so a feature
    scoped to one file finds every blanket-scoped record sitting level with
    the record that names it.
    """

    cut = len(scope)
    for mark in _WILDCARDS:
        found = scope.find(mark)
        if found != -1:
            cut = min(cut, found)
    return cut


def expand(root: Path, paths: list[str]) -> list[str]:
    """Declared globs, resolved against the files git tracks."""

    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return []
    tracked = result.stdout.splitlines()
    matched = set()
    for scope in paths:
        for path in tracked:
            if path == scope or fnmatch.fnmatchcase(path, scope):
                matched.add(path)
            elif "/" in scope and path.startswith(scope.rstrip("/*") + "/"):
                matched.add(path)
    return sorted(matched)


def _best(entry: dict[str, Any], files: list[str], weights) -> tuple[int, int, int]:
    strength = scope_strength(entry, tuple(files), weights)
    if not strength:
        return 0, 0, 0
    best_spec, best_count = 0, 0
    for scope in entry.get("scope") or []:
        covered = [f for f in files if scope_strength({"scope": [scope]}, (f,), weights)]
        if not covered:
            continue
        spec = specificity(scope)
        if (spec, len(covered)) > (best_spec, best_count):
            best_spec, best_count = spec, len(covered)
    return strength, best_spec, best_count


def attach(
    entries: list[dict[str, Any]],
    files: list[str],
    *,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    weights=None,
) -> list[dict[str, Any]]:
    """Ledger records governing these files, strongest first."""

    weights = weights if weights is not None else DEFAULTS["weights"]
    excluded = set(exclude)
    forced = set(include) - excluded
    attached = []
    for entry in entries:
        ident = str(entry.get("id", ""))
        if ident in excluded:
            continue
        strength, spec, count = _best(entry, files, weights)
        if not strength and ident not in forced:
            continue
        marked = dict(entry)
        marked["brief_strength"] = strength
        marked["brief_specificity"] = spec
        marked["brief_matches"] = count
        attached.append(marked)

    def order(entry):
        ident = str(entry.get("id", ""))
        sequence = int(ident[1:]) if ident[1:].isdigit() else 0
        return (
            -entry["brief_strength"],
            -entry["brief_specificity"],
            -entry["brief_matches"],
            sequence,
        )

    return sorted(attached, key=order)


def render(feature: dict[str, Any], attached: list[dict[str, Any]], *, limit_chars: int) -> str:
    """The feature header and the records governing it, strongest first.

    Every record line carries the three numbers that ordered it, so a rank
    the reader disagrees with is visible on the screen that shows it and one
    `docket feature amend --exclude` corrects it.
    """

    lines = [f"### {feature['id']} | {feature['slug']} [{feature['state']}] {feature['text']}"]
    for intent in feature.get("intends") or []:
        lines.append(f"intends: {intent}")
    for scope in feature.get("paths") or []:
        lines.append(f"paths: {scope}")

    head = "\n".join(lines)
    body: list[str] = []
    used = len(head)
    shown = 0
    # Reserved so the drop-count footer itself never pushes the render past
    # limit_chars: the footer is appended after this loop decides to stop,
    # so its length has to be budgeted for before that decision, not after.
    footer_reserve = len("(999 more attached record(s) past the budget; docket feature show)")
    for entry in attached:
        line = (
            f"{entry['id']} | {entry.get('kind', '')} | {entry.get('text', '')} "
            f"[strength {entry['brief_strength']}, "
            f"specificity {entry['brief_specificity']}, "
            f"matches {entry['brief_matches']}]"
        )
        if used + len(line) + 1 + footer_reserve > limit_chars and shown:
            break
        body.append(line)
        used += len(line) + 1
        shown += 1

    dropped = len(attached) - shown
    if dropped:
        body.append(f"({dropped} more attached record(s) past the budget; docket feature show)")
    return "\n".join([head, *body])


def budget_share(settings: Mapping[str, Any] | None = None) -> int:
    """The brief's slice of the context budget: a quarter of the target.

    A fixed record count would fork q100, which asks whether the character
    budget tracks the token budget it stands in for. A share moves with
    whatever q100 settles on.
    """

    cfg = settings if settings is not None else DEFAULTS
    return max(cfg["budget"]["minimum"], cfg["budget"]["target"] // 4)


def blocking(attached: list[dict[str, Any]]) -> list[str]:
    """Attached decisions whose prerequisites are unavailable.

    d109: this is the ledger's own relation, computed at
    docket/ledger.py:517-541. An open question in the feature's scope never
    blocks it. Scope overlap rests on a transient property — read by recorded
    state it fires on nearly every feature, read by the projection it fires on
    whatever files today's one open question scopes. Work stalled on a
    question is declared paused instead.
    """

    return [
        entry["id"]
        for entry in attached
        if entry.get("kind") == "decision" and not entry.get("applicable", True)
    ]


__all__ = ["attach", "blocking", "budget_share", "expand", "render", "specificity"]
