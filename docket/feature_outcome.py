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

    Walks the branch's own commits instead of diffing two trees. A single
    `git diff base...HEAD` cannot answer this: the caller has already proved
    base is an ancestor of HEAD, so the three-dot form collapses to two dots
    and carries in every file the default branch gained after the fork.
    Recomputing the base against the default branch's tip fails the other way,
    reporting nothing once the branch merges back.

    --first-parent stays on this branch's line, so a merged-in default branch
    arrives through a second parent and never counts. --no-merges drops the
    merge commits themselves, which also drops any conflict resolution made
    inside one.

    -M, because without it a rename reports as delete-old plus add-new, which
    inverts the classification when a file moves out of the declared paths.
    """

    if not base:
        raise OutcomeError(
            "docket: this feature recorded no base commit, so its change set "
            "cannot be computed; abandon it and start again now the repository "
            "has a commit"
        )
    if _git(root, "merge-base", "--is-ancestor", base, "HEAD").returncode != 0:
        raise OutcomeError(
            f"docket: {base} is no longer an ancestor of HEAD; "
            "record the outcome before squashing or rebasing the branch"
        )

    result = _git(
        root,
        "log",
        "--first-parent",
        "--no-merges",
        "--name-status",
        "-M",
        "--format=",
        f"{base}..HEAD",
    )
    if result.returncode != 0:
        raise OutcomeError(f"docket: cannot read {base}..HEAD: {result.stderr.strip()}")

    changed: list[str] = []
    renames: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if not fields or not fields[0]:
            continue
        if fields[0].startswith("R") and len(fields) == 3:
            pair = (fields[1], fields[2])
            if pair not in renames:
                renames.append(pair)
            name = fields[2]
        elif len(fields) >= 2:
            name = fields[1]
        else:
            continue
        if name not in changed:
            changed.append(name)
    return sorted(changed), renames


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


def verify_claims(
    entries: list[dict], realized: list[str], held_csv: list[str], failed_csv: list[str]
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Sort the claims the realized change set touched into held, failed, unanswered.

    Only the realized set, never the declared paths: a claim about code the
    work never touched has gained no new evidence.

    A retired claim is skipped. Something already revisited it, and asking
    again records a verdict against a line that no current view shows.
    """

    from docket import feature_brief

    touched = feature_brief.attach(entries, realized)
    claims = [
        e["id"]
        for e in touched
        if e.get("kind") == "claim"
        and not e.get("retired_by")
        and e.get("state") in ("accepted", "unassessed")
    ]
    held = [c for c in held_csv if c in claims]
    failed = [c for c in failed_csv if c in claims]
    unanswered = [c for c in claims if c not in held and c not in failed]
    return claims, held, failed, unanswered


def unattached_verdicts(claims: list[str], held_csv: list[str], failed_csv: list[str]) -> list[str]:
    """Ids a verdict named that the change set never touched.

    Dropping these in silence is the one outcome a recorder cannot detect:
    done exits 0 and the event records the claim as unanswered.
    """

    named = []
    for ident in [*held_csv, *failed_csv]:
        if ident not in claims and ident not in named:
            named.append(ident)
    return named


def verification_report(
    by_id: dict[str, dict], claims: list[str], held: list[str], failed: list[str], qualified: str
) -> list[str]:
    """One line per asked claim, then the supersession command for each failure."""

    lines = []
    for ident in claims:
        verdict = "held" if ident in held else "failed" if ident in failed else "not answered"
        lines.append(f"  claim {ident} [{verdict}]: {by_id[ident]['text']}")
    for ident in failed:
        lines.append(
            f'\ndocket claim "<the corrected proposition>" --state disputed '
            f"--supersedes {ident} \\\n"
            f'  --evidence "verified during {qualified}"'
        )
    return lines


def overlap_report(
    current: list[dict], feature_id: str, realized: list[str], terminal_states: tuple[str, ...]
) -> list[str]:
    """One advisory line per other open feature whose declared paths cover this change set.

    Two active features on different branches are allowed, the way branches
    diverge freely and conflict only at merge. This is the report at merge
    time; it never changes the exit code.
    """

    lines = []
    for other in current:
        if other["id"] == feature_id or other["state"] in terminal_states:
            continue
        shared = classify(other["paths"], realized)[0]
        if shared:
            lines.append(
                f"  overlap: {other['id']} {other['slug']} also declares {', '.join(shared[:3])}"
            )
    return lines


def is_dirty(root: Path) -> bool:
    """Whether the working tree holds uncommitted changes.

    done reads committed history, so uncommitted work would land in neither
    the intentional nor the unintentional set. .docket/ is excluded: it is
    docket's own bookkeeping, not part of the feature's realized change set,
    and a fresh feature store is always untracked the moment it is written.
    """

    return bool(_git(root, "status", "--porcelain", "--", ".", ":!.docket").stdout.strip())


__all__ = [
    "OutcomeError",
    "changed_files",
    "classify",
    "fork_point",
    "is_dirty",
    "overlap_report",
    "verification_report",
    "verify_claims",
]
