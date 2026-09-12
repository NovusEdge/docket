#!/usr/bin/env python3
"""Route a direct write to a ledger through the human.

A ledger is append-only and validated on every read, so a record written
around the CLI can break it in ways no command reports until the next
session start. This asks before any tool edits a ledger file, and says
which command does the job properly.

Reads the PreToolUse payload on stdin and prints an "ask" decision when the
call targets a ledger. Anything else exits silently, because a hook that
fails open costs a session nothing and a hook that fails closed costs it
everything.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

LEDGER_SUFFIXES = (".jsonl", ".jsonl.schema1", ".json")

# Allowlist, because a command string cannot be read for intent. Anything that
# names a ledger and is not on this list gets the prompt, including every
# inline interpreter and heredoc. Those are the constructs an edit hides in.
READERS = re.compile(
    r"^(?:cat|head|tail|less|more|wc|grep|egrep|fgrep|rg|jq|cut|sort|uniq|nl|"
    r"md5sum|sha256sum|stat|file|ls|find|diff|cmp|git|python3?\s+-m\s+json\.tool)$"
)

# The sanctioned path. `docket` alone is the installed name; bin/docket is the
# checkout. Both validate every record before they append it.
DOCKET_CLI = re.compile(r"^(?:[^\s;&|]*/)?docket(?:\.py)?$")

# A shell construct whose effect the hook cannot read at all.
OPAQUE = re.compile(
    r"(^|[\s;&|(])(?:python3?|perl|ruby|node|deno|bun|php|osascript|bash|sh|zsh)"
    r"\s+-\w*[ce]\b"
    r"|<<-?\s*['\"]?\w+"           # heredoc
    r"|\$\(|`"                      # command substitution
    r"|\beval\b|\bexec\b"
    r"|base64\s+(?:-d|--decode)"
)


def global_root() -> Path:
    if env := os.environ.get("DOCKET_HOME"):
        return Path(env).expanduser()
    if env := os.environ.get("CLAUDE_CONFIG_DIR"):
        return Path(env).expanduser() / "docket"
    return Path.home() / ".claude" / "docket"


def is_ledger(path: str, cwd: str) -> bool:
    if not path:
        return False
    try:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = Path(cwd or ".") / resolved
        resolved = Path(os.path.normpath(str(resolved)))
    except (OSError, ValueError):
        return False
    name = resolved.name
    if not name.endswith(LEDGER_SUFFIXES):
        return False
    if ".docket" in resolved.parts:
        return True
    try:
        return global_root() in resolved.parents
    except (OSError, ValueError):
        return False


def bash_targets_ledger(command: str, cwd: str) -> bool:
    """Whether a shell command naming a ledger needs the human.

    A command string does not say what it will do, so the answer is yes unless
    every segment that names a ledger is the docket CLI or a plain reader. An
    inline interpreter, a heredoc, a command substitution or an eval says
    nothing about its effect, so it always asks.
    """

    words = re.findall(r"[^\s'\"<>|;&()]+", command)
    if not any(is_ledger(word, cwd) for word in words):
        return False
    if OPAQUE.search(command):
        return True
    if ">" in command:
        return True
    for segment in re.split(r"\|\||&&|[;|&\n]", command):
        head = segment.strip().split()
        while head and ("=" in head[0] and not head[0].startswith("-")):
            head = head[1:]          # env assignments before the command
        if not head:
            continue
        name = head[0]
        if DOCKET_CLI.match(name) or READERS.match(name):
            continue
        if any(is_ledger(word, cwd) for word in head):
            return True
    return False


def targeted_path(payload: dict) -> str:
    tool = payload.get("tool_name", "")
    args = payload.get("tool_input") or {}
    cwd = payload.get("cwd", "")
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        for key in ("file_path", "notebook_path", "path"):
            value = args.get(key)
            if isinstance(value, str) and is_ledger(value, cwd):
                return value
    elif tool == "Bash":
        command = args.get("command")
        if isinstance(command, str) and bash_targets_ledger(command, cwd):
            return "the ledger named in this command"
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    target = targeted_path(payload)
    if not target:
        return 0

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"This writes {target} directly. A ledger is append-only and is "
                "validated on every read, so an edit made around the CLI can "
                "break it. Record with `docket claim`, `docket decision` or "
                "`docket question`; repair with `docket check` and `docket "
                "rebase`; convert an old ledger with `docket migrate`. Approve "
                "only if you mean to edit the file itself."
            ),
        }
    }, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
