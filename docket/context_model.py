"""Reading a projected record: coercion, state, identity, scope.

Split from docket.context to keep that file under the 300 line limit. Every
other context module reads a record through these, so a record field is
coerced the same way wherever it is read.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def _list(value: Any) -> list[Any]:
    if value is None or isinstance(value, (str, bytes)):
        return []
    if isinstance(value, Sequence):
        return list(value)
    return []


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _canonical_history(entries: list[Mapping[str, Any]]) -> str:
    return json.dumps(
        entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def _revision(entries: list[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256(_canonical_history(entries).encode("utf-8")).hexdigest()
    return digest[:12]


def _id(entry: Mapping[str, Any]) -> str:
    return _text(entry.get("id"))


def positions(entries: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Each record's index in the ledger, keyed by ID.

    Ordering keys off this rather than the ID's number because a per-kind
    counter makes d1 follow c7 in the file. Callers pass the sequence read
    from disk, which is append order; a sorted copy would reintroduce the
    numeric assumption this replaces.
    """
    return {_id(entry): index for index, entry in enumerate(entries)}


def _is_retired(entry: Mapping[str, Any]) -> bool:
    return bool(_text(entry.get("retired_by")).strip())


def _effective_state(entry: Mapping[str, Any]) -> str:
    return _text(entry.get("state") or entry.get("recorded_state") or "unknown")


def _recorded_state(entry: Mapping[str, Any]) -> str:
    return _text(entry.get("recorded_state") or entry.get("state") or "unknown")


def _clip_metadata(value: str, limit: int) -> str:
    value = value.replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _normalize_path(value: Any) -> str:
    path = _text(value).strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.casefold()


def _scope_strength(
    entry: Mapping[str, Any], files: tuple[str, ...], weights: Mapping[str, int]
) -> int:
    """Strongest scope match: exact path, then glob, then directory prefix.

    The old sort key treated every scope match as equal, so ordering between
    two matching records fell through to their position in the file.
    """

    if not files:
        return 0
    scopes = [
        _normalize_path(scope) for scope in _list(entry.get("scope")) if _normalize_path(scope)
    ]
    best = 0
    for filename in files:
        path = _normalize_path(filename)
        if not path:
            continue
        for scope in scopes:
            if "/" not in scope and not any(mark in scope for mark in "*?[]"):
                continue
            if scope == path:
                best = max(best, weights["scope_exact"])
            elif fnmatch.fnmatchcase(path, scope):
                best = max(best, weights["scope_glob"])
            elif "/" in scope and path.startswith(scope.rstrip("/") + "/"):
                best = max(best, weights["scope_prefix"])
    return best


# Feature classification calls this, so selection and classification share one
# matcher. Two matchers would let a file in the brief fall out of the
# intentional set at done.
scope_strength = _scope_strength


__all__ = [
    "scope_strength",
]
