"""The shape of a staged proposal, and the checks that run without a model.

Everything here is local. Extraction returns prose the model chose, and these
rules decide what is usable before a human is asked to read it.
"""

from __future__ import annotations

import hashlib
import re

KINDS = ("claim", "decision", "question")
STATES = ("staged", "accepted", "rejected")
CONFIDENCE = ("low", "medium", "high")

SCOPE_MAX = 200

_EMPHASIS = re.compile(r"[*_`]+")
_SPACE = re.compile(r"\s+")


class SchemaError(ValueError):
    """A proposal the local rules reject."""


def normalize_anchor(text: str) -> str:
    """The anchor reduced to what survives a model's formatting choices.

    A model asked for a verbatim line returns the words and drops the emphasis
    around them: the source reads `**Decision:** Option B` and the anchor comes
    back as `Decision: Option B`. Matching on the raw string missed a third of
    batch one for that reason alone.
    """
    return _SPACE.sub(" ", _EMPHASIS.sub("", text)).strip()


def identity(source_path: str, anchor: str) -> str:
    """The key that survives re-extraction.

    Extraction is not deterministic, so the model's own wording cannot key a
    record across runs. The anchor is verbatim source text and the path pins
    which document it came from. A NUL joins them because no path contains one,
    so no pair of (path, anchor) can collide by concatenation.
    """
    material = f"{source_path}\0{normalize_anchor(anchor)}".encode()
    return hashlib.sha256(material).hexdigest()


def invalid_scope(scope: list[str]) -> list[str]:
    """The scope entries that cannot address a file, in order.

    A model asked for a scope sometimes describes the coverage instead of
    naming it; the spike returned a 600-character paragraph ending in a glob.
    Scope feeds path matching, so an entry that is not a path is not a scope.
    """
    bad = []
    for item in scope:
        if not item or len(item) > SCOPE_MAX or _SPACE.search(item):
            bad.append(item)
    return bad


def proposal(kind: str, text: str, anchor: str, source: dict,
             choice: str = "", rationale: str = "", scope: list[str] | None = None,
             confidence: str = "low", **extra) -> dict:
    """One staged record, keyed and checked."""
    if kind not in KINDS:
        raise SchemaError(f"unknown kind {kind!r}; expected one of {', '.join(KINDS)}")
    if not text.strip():
        raise SchemaError("a proposal needs text")
    if not anchor.strip():
        raise SchemaError("a proposal needs an anchor: it is the identity key "
                          "and the reviewer's way back to the source")
    if kind == "decision" and not choice.strip():
        raise SchemaError("a decision needs a choice")
    if confidence not in CONFIDENCE:
        raise SchemaError(f"unknown confidence {confidence!r}")
    if not source.get("path"):
        raise SchemaError("a proposal needs its source path")

    scope = list(scope or [])
    bad = invalid_scope(scope)
    if bad:
        raise SchemaError(f"scope entries do not address a file: {bad!r}")

    return {
        "key": identity(source["path"], anchor),
        "kind": kind,
        "text": text,
        "choice": choice,
        "rationale": rationale,
        "scope": scope,
        "anchor": anchor,
        "source": {"path": source["path"], "date": source.get("date")},
        "confidence": confidence,
        "state": "staged",
        **extra,
    }
