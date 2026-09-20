"""Which ledger records govern a feature's declared paths.

Nothing is linked by hand. A feature declares paths, those paths expand
against the tracked tree, and every ledger record whose scope covers one of
those files attaches.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from docket.config import DEFAULTS
from docket.context import scope_strength
from docket.context_model import positions

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
    """Declared globs, resolved against the files git tracks.

    scope_strength decides the match, the same call classify() makes at done.
    A second matcher here compared paths case-sensitively while scope_strength
    casefolds both sides, so a declared path holding an uppercase letter put
    files in the brief that the intentional set then rejected.
    """

    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return []
    entry = {"scope": paths}
    weights = DEFAULTS["weights"]
    return sorted(
        path for path in result.stdout.splitlines() if scope_strength(entry, (path,), weights)
    )


def _best(entry: dict[str, Any], files: list[str], weights) -> tuple[int, int, int]:
    # Score every scope on its own, then read all three numbers off the scopes
    # that reached the top strength. Taking the strength from one scope and the
    # specificity from another described two different globs in one line, and
    # let a record borrow a high specificity from a weak scope to win a tie its
    # strong scope did not earn.
    scored: list[tuple[int, int, int]] = []
    for scope in entry.get("scope") or []:
        covered = sum(1 for f in files if scope_strength({"scope": [scope]}, (f,), weights))
        if covered:
            scored.append(
                (
                    scope_strength({"scope": [scope]}, tuple(files), weights),
                    specificity(scope),
                    covered,
                )
            )
    if not scored:
        return 0, 0, 0
    strength = max(item[0] for item in scored)
    best_spec, best_count = max((s, c) for hit, s, c in scored if hit == strength)
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
        marked["brief_forced"] = ident in forced
        attached.append(marked)

    at = positions(entries)

    def order(entry):
        ident = str(entry.get("id", ""))
        sequence = at.get(ident, 0)
        # A forced record sorts first. Its strength is often 0, because the
        # globs missed it, which is the reason somebody named it by id. Ranking
        # it by that 0 puts it last and the budget drops it first.
        return (
            0 if entry["brief_forced"] else 1,
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
    footer_reserve = len(
        "(999 more attached record(s) past the budget; raise --detail or narrow the paths)"
    )
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
        body.append(
            f"({dropped} more attached record(s) past the budget; raise --detail or narrow the paths)"
        )
    return "\n".join([head, *body])


def budget_share(settings: Mapping[str, Any] | None = None) -> int:
    """The brief's slice of the context budget: a quarter of the target.

    A fixed record count would fork q100, which asks whether the character
    budget tracks the token budget it stands in for. A share moves with
    whatever q100 settles on.
    """

    cfg = settings if settings is not None else DEFAULTS
    return max(cfg["budget"]["minimum"], cfg["budget"]["target"] // 4)


def with_blocked(current: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    """Overlay the derived blocked state on every open feature."""
    from docket import env, features, ledger

    entries = ledger.project(ledger.read(env.ledger_path()), validated=True)
    for feature in current:
        if feature["state"] in features.TERMINAL_STATES:
            continue
        files = expand(root, feature["paths"])
        attached = attach(entries, files, include=feature["include"], exclude=feature["exclude"])
        blockers = blocking(attached)
        if blockers:
            feature["state"] = "blocked"
            feature["blocked_by"] = blockers
    return current


def blocking(attached: list[dict[str, Any]]) -> list[str]:
    """Attached decisions whose prerequisites are unavailable.

    d109: this is the ledger's own relation, computed at
    docket/ledger.py:517-541. An open question in the feature's scope never
    blocks it. Work stalled on a question is declared paused instead.

    applicable is False for two unrelated reasons. A retired or revoked
    decision carries blocked_by == [its own id]. A decision whose
    prerequisites are unmet carries the ids of those prerequisites. Only the
    second is a blocker. Reading applicable alone made every supersession in
    scope block the feature, which on this repository was eight false
    positives and no true ones.
    """

    return [
        entry["id"]
        for entry in attached
        if entry.get("kind") == "decision"
        and not entry.get("applicable", True)
        and [ident for ident in entry.get("blocked_by") or [] if ident != entry["id"]]
    ]


__all__ = ["attach", "blocking", "budget_share", "expand", "render", "specificity", "with_blocked"]
