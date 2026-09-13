import os
import sys


def _match(e: dict, term: str) -> bool:
    term = term.lower()
    return term in e.get("text", "").lower() or term in e.get("choice", "").lower()


# Duplicated from install.py:30-61 rather than imported: bin/docket ships and
# runs standalone, so it cannot assume install.py sits beside it.
#
# An agent env var (the same names author() checks) forces colour off even on
# a real tty. Cursor, Copilot in VS Code, and Windsurf run agent shell
# commands over node-pty, so isatty() alone reads as "human" there. Wrongly
# guessing pretty puts escape codes in a model's context window; wrongly
# guessing plain costs a person one flag, so the asymmetry decides it.
_AGENT_ENV_VARS = (
    "CLAUDE_SESSION_ID", "CLAUDE_CODE_BRIDGE_SESSION_ID", "SESSION_ID",
    "AI_AGENT", "CODEX_SANDBOX", "CODEX_HOME",
)


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt" and not os.environ.get("WT_SESSION"):
        return False
    if any(os.environ.get(v) for v in _AGENT_ENV_VARS):
        return False
    return True


def _use_glyphs() -> bool:
    enc = getattr(sys.stdout, "encoding", None) or ""
    try:
        "●".encode(enc)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


_STATE_COLOR = {
    "accepted": "2", "adopted": "2", "resolved": "2",
    "rejected": "1", "revoked": "1", "disputed": "1",
    "unassessed": "3", "open": "3",
}  # green, red, yellow
_DIM = "8"

_GRAPH_GLYPHS = {
    "bullet": "●", "open": "○", "retired": "⊘", "vert": "│", "tee": "├─ ", "elbow": "└─ ",
    "hbar": "─", "ltee": "├", "join": "┴", "cross": "┼", "corner": "╯",
}
_GRAPH_GLYPHS_ASCII = {
    "bullet": "*", "open": "o", "retired": "x", "vert": "|", "tee": "+- ", "elbow": "`- ",
    "hbar": "-", "ltee": "+", "join": "+", "cross": "+", "corner": "'",
}


def _c(code: str, text: str, use_color: bool) -> str:
    return "\033[3%sm%s\033[0m" % (code, text) if use_color else text
