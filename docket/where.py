"""The query language behind --where and the graph viewer's filter.

`docket list`, `docket graph`, and the viewer's callback `docket _filter-ids`
all parse here, so a query means the same thing everywhere. The viewer repeats
only the tokenizer and the text term, in graph/filter.go; a change to either
must land in both files.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from docket.config import DEFAULTS
from docket.context_model import _list, _normalize_path, scope_strength
from docket.ledger import KINDS, STATES

FIELDS = ("after", "author", "before", "branch", "is", "kind", "scope", "state")
IS_VALUES = ("blocked", "corrected", "pinned", "retired")
STATE_VALUES = tuple(sorted({state for values in STATES.values() for state in values}))
_TEXT_KEYS = ("id", "text", "choice", "rationale")
_FIELD_RE = re.compile(r"[A-Za-z]+")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# The defaults, never the configured weights: a weight set to zero in
# config.toml would silently turn scope matching off.
_WEIGHTS = DEFAULTS["weights"]


class WhereError(ValueError):
    """A query that names an unknown field or value, or a date not in YYYY-MM-DD."""


@dataclass(frozen=True)
class Term:
    field: str  # empty for a text term
    value: str
    negated: bool


@dataclass(frozen=True)
class Query:
    terms: tuple[Term, ...] = ()

    @property
    def wants_retired(self) -> bool:
        return any(t.field == "is" and t.value == "retired" and not t.negated for t in self.terms)

    @property
    def has_fields(self) -> bool:
        return any(t.field for t in self.terms)

    def matches(self, entry: Mapping[str, Any]) -> bool:
        groups: dict[str, bool] = {}
        for term in self.terms:
            hit = _hit(term, entry)
            if term.negated:
                if hit:
                    return False
            elif term.field in ("", "is"):
                if not hit:
                    return False
            else:
                groups[term.field] = groups.get(term.field, False) or hit
        return all(groups.values())


def parse(query: str) -> Query:
    return Query(tuple(_term(negated, body, colon) for negated, body, colon in _split(query)))


def _split(query: str) -> list[tuple[bool, str, int]]:
    """Each term as (negated, body, colon).

    Quotes are removed from body and may hold whitespace; an unclosed quote
    runs to the end. colon indexes the first ':' that comes before any quote,
    or is -1, which keeps `"d12:"` a text term.
    """
    parts: list[tuple[bool, str, int]] = []
    i, n = 0, len(query)
    while i < n:
        if query[i].isspace():
            i += 1
            continue
        negated = query[i] == "-" and i + 1 < n and not query[i + 1].isspace()
        if negated:
            i += 1
        body, colon, quoted = "", -1, False
        while i < n and not query[i].isspace():
            if query[i] == '"':
                quoted = True
                end = query.find('"', i + 1)
                end = n if end == -1 else end
                body += query[i + 1 : end]
                i = end + 1
                continue
            if query[i] == ":" and colon == -1 and not quoted:
                colon = len(body)
            body += query[i]
            i += 1
        parts.append((negated, body, colon))
    return parts


def _term(negated: bool, body: str, colon: int) -> Term:
    if colon <= 0 or not _FIELD_RE.fullmatch(body[:colon]):
        return Term("", body.lower(), negated)
    field, value = body[:colon].lower(), body[colon + 1 :]
    shown = ("-" if negated else "") + body
    if field not in FIELDS:
        raise _fail(
            shown,
            f"unknown field {field}; use {', '.join(FIELDS)}, or quote the term to search text",
        )
    if not value:
        raise _fail(shown, "needs a value")
    if field in ("after", "before"):
        _day(shown, value)
        return Term(field, value, negated)
    if field == "scope":
        return Term(field, value, negated)
    value = value.lower()
    if field == "kind" and value not in KINDS:
        raise _fail(shown, f"unknown kind {value}; use {', '.join(KINDS)}")
    if field == "state" and value in ("retired", "blocked"):
        raise _fail(shown, f"use is:{value}")
    if field == "state" and value not in STATE_VALUES:
        raise _fail(shown, f"unknown state {value}; use {', '.join(STATE_VALUES)}")
    if field == "is" and value not in IS_VALUES:
        raise _fail(shown, f"unknown is:{value}; use {', '.join(IS_VALUES)}")
    return Term(field, value, negated)


def _fail(term: str, message: str) -> WhereError:
    return WhereError(f"docket: where: {term}: {message}")


def _day(term: str, value: str) -> date:
    if _DATE_RE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise _fail(term, "dates are YYYY-MM-DD")


def _hit(term: Term, entry: Mapping[str, Any]) -> bool:
    field, value = term.field, term.value
    if not field:
        return any(value in str(entry.get(key) or "").lower() for key in _TEXT_KEYS)
    if field in ("kind", "state"):
        return str(entry.get(field) or "").lower() == value
    if field in ("author", "branch"):
        return value in str(entry.get(field) or "").lower()
    if field == "is":
        return _is(value, entry)
    if field == "scope":
        return _scope(value, entry)
    day = _ts_day(entry.get("ts"))
    if day is None:
        return False
    limit = date.fromisoformat(value)
    return day >= limit if field == "after" else day < limit


def _is(value: str, entry: Mapping[str, Any]) -> bool:
    if value == "pinned":
        return bool(entry.get("pinned"))
    if value == "corrected":
        return bool(entry.get("corrections"))
    if value == "retired":
        return bool(entry.get("retired_by"))
    # The viewer's rule, graph/model.go decisionCondition. blocked_by cannot
    # decide it: project() sets blocked_by to the record's own id for every
    # retired or revoked decision.
    return (
        entry.get("kind") == "decision"
        and entry.get("recorded_state", entry.get("state")) == "adopted"
        and not entry.get("retired_by")
        and entry.get("applicable") is False
    )


def _scope(value: str, entry: Mapping[str, Any]) -> bool:
    path = _normalize_path(value)
    scopes = [_normalize_path(item) for item in _list(entry.get("scope"))]
    if path.endswith("/"):
        folder = path.rstrip("/")
        if any(item.startswith(path) or item == folder for item in scopes):
            return True
        return scope_strength(entry, (folder,), _WEIGHTS) > 0
    # scope_strength skips a top-level entry with no "/" and no glob, so a
    # file such as README.md needs the equality test.
    return path in scopes or scope_strength(entry, (path,), _WEIGHTS) > 0


def _ts_day(raw: Any) -> date | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).date()


__all__ = ["FIELDS", "IS_VALUES", "Query", "STATE_VALUES", "Term", "WhereError", "parse"]
