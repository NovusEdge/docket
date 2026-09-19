"""The working tree's proxy for the task a briefing should be scoped to.

Split from docket.cli.query to keep that file under the 300 line limit. Every
other command in that module takes its scope from the caller.
"""

from __future__ import annotations

import subprocess

_AUTO_SCOPE_LIMIT = 50


def auto_scope_files(limit: int = _AUTO_SCOPE_LIMIT) -> tuple[str, ...]:
    """Changed and untracked paths, as the working tree's proxy for a task.

    Both commands run from the repository root. git ls-files lists only what
    sits under the current directory, and git diff prints root-relative paths,
    so running from a subdirectory would drop files and mix two path bases.
    -z output, because a path may contain a newline.
    """

    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=3
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if top.returncode != 0:
        return ()
    root = top.stdout.strip()

    groups: list[list[str]] = []
    for command in (
        ["git", "diff", "--name-only", "-z", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
    ):
        try:
            # Bytes, not text: the locale codec decodes strictly, and a path
            # carrying an invalid byte would raise UnicodeDecodeError, which is
            # neither OSError nor SubprocessError and would kill every
            # docket context in that repository.
            done = subprocess.run(command, cwd=root, capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            return ()
        # A repository with no commits has no HEAD, so the diff fails while
        # ls-files still reports every untracked file. Skip the failed command
        # and keep what the other one found.
        if done.returncode != 0:
            groups.append([])
            continue
        text = done.stdout.decode("utf-8", errors="surrogateescape")
        # git collapses an untracked nested repository to a directory entry
        # with a trailing slash. A scope matches files, so such an entry can
        # never match and would spend a slot in the cap.
        groups.append([path for path in text.split("\0") if path and not path.endswith("/")])

    # Interleave the two sources. Taking the head of a concatenated list let a
    # branch with more than `limit` modified files starve every untracked one,
    # which is the work in progress.
    paths: list[str] = []
    for index in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if index < len(group) and group[index] not in paths:
                paths.append(group[index])

    if not paths:
        # A clean tree says nothing about the task. The last commit does, and it
        # is the likeliest starting point for the next piece of work. --root
        # keeps a first commit readable, and -m keeps a merge readable, because
        # a combined diff prints nothing for either.
        try:
            done = subprocess.run(
                [
                    "git",
                    "diff-tree",
                    "-m",
                    "--root",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    "-z",
                    "HEAD",
                ],
                cwd=root,
                capture_output=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return ()
        # A repository with no commits has no HEAD, so git exits non-zero and
        # the briefing stays unscoped.
        if done.returncode == 0:
            text = done.stdout.decode("utf-8", errors="surrogateescape")
            # -m prints one diff per parent, so a merge repeats a path.
            paths = list(
                dict.fromkeys(path for path in text.split("\0") if path and not path.endswith("/"))
            )
    return tuple(paths[:limit])


__all__ = ["auto_scope_files"]
