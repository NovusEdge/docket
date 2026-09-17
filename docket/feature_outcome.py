"""What a feature's work actually changed, measured against what it declared.

The declared paths state the intended blast radius before work starts. This
module compares them with the branch's realized change set.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from docket.config import DEFAULTS
from docket.context import scope_strength

DEFAULT_BRANCHES = ("main", "master")


class OutcomeError(ValueError):
    """Git could not answer a question this module needs answered."""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OutcomeError(f"docket: git {' '.join(args)} failed: {exc}") from exc


def _current_branch(root: Path) -> str:
    return _git(root, "branch", "--show-current").stdout.strip()


def fork_point(root: Path) -> tuple[str, str]:
    """The merge base with the default branch, and a warning when there is none.

    HEAD is the wrong base. A feature declared after work began would miss
    every commit that came first, and its unintentional set would be silently
    short.
    """

    current = _current_branch(root)
    for candidate in DEFAULT_BRANCHES:
        if _git(root, "rev-parse", "--verify", candidate).returncode != 0:
            continue
        if candidate == current:
            break
        result = _git(root, "merge-base", "HEAD", candidate)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip(), ""

    head = _git(root, "rev-parse", "HEAD")
    if head.returncode != 0:
        return (
            "",
            "recording no base: this repository has no commits yet",
        )
    return (
        head.stdout.strip(),
        "recording HEAD as the base: this is the default branch, so there is no fork point",
    )


def changed_files(root: Path, base: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Files this branch changed since the fork point, with renames named.

    Three dots, because two dots diffs two trees: a branch that merged the
    default branch in would report every upstream file as its own change.
    -M, because without it a rename reports as delete-old plus add-new, which
    inverts the classification when a file moves out of the declared paths.
    """

    if _git(root, "merge-base", "--is-ancestor", base, "HEAD").returncode != 0:
        raise OutcomeError(
            f"docket: {base} is no longer an ancestor of HEAD; "
            "record the outcome before squashing or rebasing the branch"
        )

    # base is already an ancestor of HEAD by the check above, so a three-dot
    # diff against it collapses to a two-dot diff and stops excluding commits
    # the default branch gained after the feature forked. Recompute the merge
    # base against the default branch's current tip instead.
    diff_base = base
    current = _current_branch(root)
    for candidate in DEFAULT_BRANCHES:
        if candidate == current or _git(root, "rev-parse", "--verify", candidate).returncode != 0:
            continue
        merge_base = _git(root, "merge-base", "HEAD", candidate)
        if merge_base.returncode == 0 and merge_base.stdout.strip():
            diff_base = merge_base.stdout.strip()
            break

    result = _git(root, "diff", "--name-status", "-M", f"{diff_base}...HEAD")
    if result.returncode != 0:
        raise OutcomeError(f"docket: cannot diff {base}...HEAD: {result.stderr.strip()}")

    changed: list[str] = []
    renames: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if not fields or not fields[0]:
            continue
        if fields[0].startswith("R") and len(fields) == 3:
            renames.append((fields[1], fields[2]))
            changed.append(fields[2])
        elif len(fields) >= 2:
            changed.append(fields[1])
    return changed, renames


def classify(paths: list[str], changed: list[str]) -> tuple[list[str], list[str]]:
    """Split a change set into what the declared paths cover and what they miss."""

    weights = DEFAULTS["weights"]
    entry = {"scope": paths}
    intentional, unintentional = [], []
    for path in changed:
        if scope_strength(entry, (path,), weights):
            intentional.append(path)
        else:
            unintentional.append(path)
    return intentional, unintentional


def is_dirty(root: Path) -> bool:
    """Whether the working tree holds uncommitted changes.

    done reads committed history, so uncommitted work would land in neither
    the intentional nor the unintentional set. .docket/ is excluded: it is
    docket's own bookkeeping, not part of the feature's realized change set,
    and a fresh feature store is always untracked the moment it is written.
    """

    return bool(_git(root, "status", "--porcelain", "--", ".", ":!.docket").stdout.strip())


__all__ = ["OutcomeError", "changed_files", "classify", "fork_point", "is_dirty"]
