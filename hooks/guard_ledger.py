#!/usr/bin/env python3
"""Route a direct write to a ledger through the human.

A ledger is append-only and validated on every read, so a record written
around the CLI can break it in ways no command reports until the next
session start. This asks before any tool edits a ledger file, and says
which command does the job properly.

Reads the PreToolUse payload on stdin and prints an "ask" decision when the
call targets a ledger. For an edit of any other file it adds context naming
the recorded decisions whose scope covers that file, once per session, and on
the session's third distinct edited file with no feature open it says to start
one. Every other call exits silently.

This catches routine edits, not a determined one. Eval, a script that writes
the ledger, a variable holding the path or other indirection can still write
it; the hook prevents accidents and does not enforce append-only.

DOCKET_HOOKS=off is the human's opt-out: the hook exits silently for every
call, ledger writes included.

A hook that fails open costs a session nothing and a hook that fails closed
costs it everything.
"""

from __future__ import annotations

import contextlib
import fnmatch
import io
import json
import os
import re
import sys
import time
from pathlib import Path

# migrate keeps the original at ledger.jsonl.schemaN, N the starting version,
# so a fixed suffix list goes stale with every schema bump.
LEDGER_NAME = re.compile(r"\.(?:jsonl(?:\.schema[0-9]+)?|json)$")
GLOB_SAMPLES = ("ledger.jsonl", "ledger.jsonl.schema1", "features.jsonl", "migration-v0.8-map.json")

# Allowlist, because a command string cannot be read for intent. Anything that
# names a ledger and is not on this list gets the prompt, including every
# inline interpreter and heredoc. Those are the constructs an edit hides in.
READERS = re.compile(
    r"^(?:cd|cat|head|tail|less|more|wc|grep|egrep|fgrep|rg|jq|cut|sort|uniq|nl|"
    r"md5sum|sha256sum|stat|file|ls|find|diff|cmp|git|python3?\s+-m\s+json\.tool)$"
)

# Four of the readers write when asked to. `git restore` and `git checkout --`
# rewrite a tracked ledger from history, `find -delete` removes it, `sort -o`
# and `uniq in out` write over it. The name alone settles nothing for these, so
# their arguments decide.
# add, stage and commit copy the file into the index and object store and leave
# the working copy alone; committing the ledger with its work is the documented
# workflow, so asking there trains people to approve the prompt blind.
GIT_LEAVES_FILE = frozenset(
    {
        "add",
        "blame",
        "cat-file",
        "commit",
        "diff",
        "grep",
        "log",
        "ls-files",
        "ls-tree",
        "rev-list",
        "rev-parse",
        "show",
        "shortlog",
        "stage",
        "status",
    }
)

FIND_WRITE_ACTIONS = frozenset(
    {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf"}
)


# Global options that take a separate value. Without these, the value of `git
# -C path log` reads as the subcommand.
GIT_VALUE_OPTIONS = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
)


def _git_writes(args: list[str]) -> bool:
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in GIT_VALUE_OPTIONS:
            skip = True
            continue
        if arg.startswith("-"):
            continue
        return arg not in GIT_LEAVES_FILE
    return False


def _sort_writes(args: list[str]) -> bool:
    # -o bundles, so `sort -uo FILE` writes FILE. Any short cluster ending in o
    # counts, which also catches `-ko` at the cost of a prompt nobody minds.
    return any(re.fullmatch(r"-[A-Za-z]*o", arg) or arg.startswith("--output") for arg in args)


def _uniq_writes(args: list[str]) -> bool:
    # uniq INPUT OUTPUT writes the second operand.
    return sum(1 for arg in args if not arg.startswith("-")) > 1


WRITE_MODES = {
    "git": _git_writes,
    "find": lambda args: any(arg in FIND_WRITE_ACTIONS for arg in args),
    "sort": _sort_writes,
    "uniq": _uniq_writes,
}

# The sanctioned path. `docket` alone is the installed name; bin/docket is the
# checkout. Both validate every record before they append it.
DOCKET_CLI = re.compile(r"^(?:[^\s;&|]*/)?docket(?:\.py)?$")

# A shell construct whose effect the hook cannot read at all.
OPAQUE = re.compile(
    r"(^|[\s;&|(])(?:python3?|perl|ruby|node|deno|bun|php|osascript|bash|sh|zsh)"
    r"\s+-\w*[ce]\b"
    r"|<<-?\s*['\"]?\w+"  # heredoc
    r"|\$\(|`"  # command substitution
    r"|\beval\b|\bexec\b"
    r"|base64\s+(?:-d|--decode)"
)

# A quoted delimiter makes the body literal: the shell expands nothing in it.
# Commit tooling passes messages this way, through `-F -` or `-m "$(cat <<'EOF'
# ...)"`, and a message about ledger work names the ledger and quotes backticks.
# The body ends at the first line holding only the tag; matching trailing blanks
# can only end it earlier than the shell does, which leaves more text to check.
_QUOTED_HEREDOC = (
    r"<<-?[ \t]*(?P<q>['\"])(?P<tag>\w+)(?P=q)(?P<rest>[^\n]*)\n"
    r"(?:.*?\n)??[ \t]*(?P=tag)[ \t]*(?=\n|$)"
)
CAT_MESSAGE = re.compile(r"\$\(\s*cat\s+" + _QUOTED_HEREDOC + r"\s*\)", re.S)
HEREDOC_MESSAGE = re.compile(_QUOTED_HEREDOC, re.S)

# Writes nothing: discarding to /dev/null, or duplicating one descriptor onto another.
HARMLESS_REDIRECT = re.compile(r"(?:&|\d*)>>?\s*/dev/null\b|\d*>&(?:\d+|-)")

SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|&\n]")


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
    # A glob under .docket may expand to the ledger: `>> .docket/l*`.
    if ".docket" in resolved.parts and any(c in name for c in "*?["):
        return any(fnmatch.fnmatchcase(n, name) for n in GLOB_SAMPLES)
    # The directory counts as a target. A command can name the ledger by a
    # pattern it never spells out, as `find .docket -name 'ledger.jsonl'` does.
    if name == ".docket":
        return True
    if not LEDGER_NAME.search(name):
        return False
    if ".docket" in resolved.parts:
        return True
    try:
        return global_root() in resolved.parents
    except (OSError, ValueError):
        return False


def _names_ledger(word: str, cwd: str) -> bool:
    """Whether a shell word names a ledger, plain or as --flag=path."""
    if is_ledger(word, cwd):
        return True
    _, sep, value = word.partition("=")
    return bool(sep and value) and is_ledger(value, cwd)


def bash_targets_ledger(command: str, cwd: str) -> bool:
    """Whether a shell command naming a ledger needs the human.

    A command string does not say what it will do, so the answer is yes unless
    every segment that names a ledger is the docket CLI or a plain reader. An
    inline interpreter, a heredoc, a command substitution or an eval says
    nothing about its effect, so it always asks.
    """

    segments = _segments_with_cwd(command, cwd)
    if not any(_names_ledger(word, seg_cwd) for seg, seg_cwd in segments for word in _words(seg)):
        if not any(_names_ledger(word, cwd) for word in _words(command)):
            return False
    command = _drop_git_messages(command)
    if OPAQUE.search(command):
        return True
    if ">" in HARMLESS_REDIRECT.sub("", command):
        return True
    for segment, cwd in _segments_with_cwd(command, cwd):
        head = _command_words(segment)
        if not head:
            continue
        name = head[0]
        writes = WRITE_MODES.get(Path(name).name)
        if writes and writes(head[1:]):
            return True
        if DOCKET_CLI.match(name) or READERS.match(name):
            continue
        if any(_names_ledger(word, cwd) for word in head):
            return True
    return False


def _words(text: str) -> list[str]:
    return re.findall(r"[^\s'\"<>|;&()]+", text)


def _segments_with_cwd(command: str, cwd: str) -> list[tuple[str, str]]:
    """Split a command into segments, each with the directory it runs in.

    Only a plain `cd DIR` segment moves the directory; `cd` with no argument, `-`
    or `~` leaves it, which can only miss a ledger, never invent one.
    """
    out = []
    for segment in SEGMENT_SPLIT.split(command):
        out.append((segment, cwd))
        head = _command_words(segment)
        if len(head) == 2 and head[0] == "cd":
            target = head[1].strip("'\"")
            if target and not target.startswith(("-", "~", "$")):
                cwd = os.path.normpath(os.path.join(cwd or ".", target))
    return out


def _command_words(segment: str) -> list[str]:
    words = segment.strip().split()
    while words and ("=" in words[0] and not words[0].startswith("-")):
        words = words[1:]  # env assignments before the command
    return words


def _drop_git_messages(command: str) -> str:
    """Remove quoted-heredoc commit messages that feed a git command."""

    def feeds_git(match: re.Match[str]) -> bool:
        words = _command_words(SEGMENT_SPLIT.split(match.string[: match.start()])[-1])
        return bool(words) and Path(words[0]).name == "git"

    command = CAT_MESSAGE.sub(lambda m: "MESSAGE" if feeds_git(m) else m.group(0), command)
    return HEREDOC_MESSAGE.sub(lambda m: m.group("rest") if feeds_git(m) else m.group(0), command)


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


FILE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
MAX_RECORDS = 8
HEADLINE = 90
SEEN_TTL = 7 * 24 * 3600
WILDCARDS = "*?[]"


def _session(payload: dict) -> str:
    # Claude Code puts session_id in every hook payload. The environment names
    # are the ones docket.env.session_id reads, for harnesses that do not;
    # importing it would load the whole ledger module on every edit.
    candidates = (payload.get("session_id"),) + tuple(
        os.environ.get(var)
        for var in ("CLAUDE_SESSION_ID", "CLAUDE_CODE_BRIDGE_SESSION_ID", "SESSION_ID")
    )
    for value in candidates:
        if isinstance(value, str) and value:
            return re.sub(r"[^\w.-]", "_", value)
    return ""


def _seen_file(session: str) -> Path:
    # Per-user state, not the repository: the hook must not dirty a tree or need
    # a gitignore entry, and the session's own id keys it so no cleanup is
    # needed beyond ageing out old files.
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "docket" / "hook-seen" / session


def _was_seen(path: Path, rel: str) -> bool:
    try:
        return rel in path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False


def _mark_seen(path: Path, rel: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(rel + "\n")
    if fresh:
        cutoff = time.time() - SEEN_TTL
        for old in path.parent.iterdir():
            try:
                if old.stat().st_mtime < cutoff:
                    old.unlink()
            except OSError:
                pass


def _project_root(start: Path) -> Path:
    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return start


def _ledger_file(cwd: Path, root: Path) -> Path:
    # Mirrors docket.env.ledger_path, which cannot be imported without loading
    # the ledger module.
    for directory in (cwd, *cwd.parents):
        candidate = directory / ".docket" / "ledger.jsonl"
        if candidate.exists():
            return candidate
        if directory == root:
            break
    slug = str(root).replace("/", "-").replace("\\", "-").strip("-") or "root"
    return global_root() / slug / "ledger.jsonl"


def _ancestors(rel: str) -> list[str]:
    parts = rel.split("/")
    return ["/".join(parts[:n]) for n in range(2, len(parts))]


def _covers(scope: str, rel: str) -> bool:
    """An exact file scope, or a directory scope at least two levels deep.

    `docs/**` or `hooks/` governs a whole top-level tree, so it would attach to
    nearly every edit there and drown the records that name the file.
    """
    scope = scope.strip().replace("\\", "/").casefold()
    while scope.startswith("./"):
        scope = scope[2:]
    if scope == rel:
        return True
    if scope.endswith("/**"):
        base = scope[:-3]
    elif scope.endswith("/"):
        base = scope.rstrip("/")
    else:
        return False
    if "/" not in base or any(mark in base for mark in WILDCARDS):
        return False
    return rel.startswith(base + "/")


def _clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= HEADLINE else text[: HEADLINE - 3] + "..."


def _edit_target(payload: dict) -> tuple[str, Path, Path, str] | None:
    """The edited path as given, the cwd, the project root, and the casefolded relative path."""
    args = payload.get("tool_input") or {}
    value = next((args[k] for k in ("file_path", "notebook_path", "path") if args.get(k)), "")
    if not isinstance(value, str):
        return None
    cwd = Path(os.path.normpath(payload.get("cwd") or "."))
    root = _project_root(cwd)
    target = Path(os.path.normpath(cwd / value))
    try:
        rel = target.relative_to(root).as_posix().casefold()
    except ValueError:
        return None
    return value, cwd, root, rel


def governing_context(payload: dict) -> str:
    edit = _edit_target(payload)
    if not edit:
        return ""
    value, cwd, root, rel = edit

    session = _session(payload)
    seen = _seen_file(session) if session else None
    if seen and _was_seen(seen, rel):
        return ""

    ledger = _ledger_file(cwd, root)
    try:
        text = ledger.read_text(encoding="utf-8").casefold()
    except OSError:
        return ""
    # A record can only cover this file if the ledger names the file or one of
    # its directories somewhere, and a correction that changes a scope names it
    # too. Most edits stop here and never pay for the docket import.
    if not any(needle in text for needle in (rel, *_ancestors(rel))):
        return ""

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from docket import ledger as store

    with contextlib.redirect_stderr(io.StringIO()):
        entries = store.project(store.read(ledger, lock=False), validated=True)
    hits = [
        e
        for e in entries
        if not e.get("retired_by") and any(_covers(s, rel) for s in e.get("scope") or [])
    ]
    if not hits:
        return ""

    if seen:
        _mark_seen(seen, rel)
    lines = [
        f"Recorded decisions govern {value}; read one with `docket show ID`:",
        *(
            f"{e['id']} {e['kind']} {e.get('state', '')}: {_clip(e.get('text', ''))}"
            for e in hits[:MAX_RECORDS]
        ),
    ]
    if len(hits) > MAX_RECORDS:
        lines.append(f"+{len(hits) - MAX_RECORDS} more")
    return "\n".join(lines)


NUDGE_AT = 3
NUDGED = ":nudged"


def _open_feature(store: Path) -> bool:
    if not store.exists():
        return False
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from docket import feature_project, features

    current = feature_project.project(features.read(store, lock=False))
    return any(f["state"] not in features.TERMINAL_STATES for f in current)


def feature_nudge(payload: dict) -> str:
    """The start-a-feature prompt, on the session's third distinct edited file.

    The session-start hint sees only a tree that is already dirty, and fresh
    sessions and worktree agents start clean, so this is the prompt that
    reaches work as it becomes multi-file. Without a session id there is
    nothing to count against, so it stays quiet.
    """
    session = _session(payload)
    edit = _edit_target(payload)
    if not session or not edit:
        return ""
    _, cwd, root, rel = edit
    if rel.startswith(".docket/"):
        return ""
    edits = _seen_file(session).parent / f"{session}.edits"
    try:
        files = edits.read_text(encoding="utf-8").splitlines()
    except OSError:
        files = []
    if NUDGED in files or rel in files:
        return ""
    files.append(rel)
    _mark_seen(edits, rel)
    if len(files) < NUDGE_AT:
        return ""
    # Marked before the store is read, so the docket import runs at most once
    # per session, whatever the store says.
    _mark_seen(edits, NUDGED)
    ledger = _ledger_file(cwd, root)
    if not ledger.exists() or _open_feature(ledger.parent / "features.jsonl"):
        return ""
    command = Path(__file__).resolve().parent.parent / "bin" / "docket"
    return (
        f"This session has edited {len(files)} files ({', '.join(files)}) and no docket "
        "feature is open. Start one before the next edit, so the change set is declared "
        f'and `done` can check it: `{command} feature start SLUG --text "what this work '
        "changes\" --path 'DIR/**'`. Load the docket-feature skill for path rules and "
        "closing with done."
    )


LEDGER_GUIDANCE = (
    "Do not edit the ledger file. Record a new claim, decision or question with "
    "`docket record` (or `docket claim`, `docket decision`, `docket question`); "
    "fix a recorded field with `docket correct`; replace a record by recording its "
    "successor with `--supersedes ID`; repair with `docket check` and `docket "
    "rebase`; convert an old ledger with `docket migrate`."
)


def main() -> int:
    if os.environ.get("DOCKET_HOOKS") == "off":
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    target = targeted_path(payload)
    if target:
        output = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"This writes {target} directly. A ledger is append-only and is "
                "validated on every read, so an edit made around the CLI can "
                "break it. Record with `docket claim`, `docket decision` or "
                "`docket question`; fix a recorded field with `docket correct`; "
                "repair with `docket check` and `docket "
                "rebase`; convert an old ledger with `docket migrate`. Approve "
                "only if you mean to edit the file itself."
            ),
            "additionalContext": LEDGER_GUIDANCE,
        }
    elif payload.get("tool_name") in FILE_TOOLS:
        # Fails open: a docket error must never cost an edit.
        parts = []
        for build in (governing_context, feature_nudge):
            try:
                parts.append(build(payload))
            except Exception:
                pass
        context = "\n\n".join(filter(None, parts))
        if not context:
            return 0
        output = {"hookEventName": "PreToolUse", "additionalContext": context}
    else:
        return 0

    json.dump({"hookSpecificOutput": output}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
