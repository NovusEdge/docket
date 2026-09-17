"""An append-only record of work in flight, kept beside the decision ledger.

The ledger records what was settled. This file records what is underway: a
named piece of work, the paths it declares, the outcomes it intends, and the
change set it realized. Nothing here reads or writes a ledger record.

Every line is an event. Current state is a projection over them.
"""

from __future__ import annotations

import copy
import re
from typing import Any

SCHEMA = 1
EVENTS = ("start", "amend", "note", "done", "abandon")
STATUSES = ("active", "paused", "review")
TERMINAL_STATES = ("done", "abandoned")

ID_RE = re.compile(r"f(0|[1-9][0-9]*)$")
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*$")

DEFAULTS: dict[str, Any] = {
    "schema": SCHEMA,
    "id": "",
    "event": "",
    "slug": "",
    "status": "",
    "text": "",
    "paths": [],
    "intends": [],
    "include": [],
    "exclude": [],
    "base": "",
    "branch": "",
    "ts": "",
    "session": "",
    "author": "",
    "intentional": [],
    "unintentional": [],
    "renamed_out": [],
}
ALLOWED_FIELDS = frozenset(DEFAULTS)

_STRING_FIELDS = (
    "id",
    "event",
    "slug",
    "status",
    "text",
    "base",
    "branch",
    "ts",
    "session",
    "author",
)
_LIST_FIELDS = (
    "paths",
    "intends",
    "include",
    "exclude",
    "intentional",
    "unintentional",
    "renamed_out",
)


class FeatureError(ValueError):
    """A feature event that cannot be used as written."""


def _error(where: str, message: str) -> FeatureError:
    return FeatureError(f"docket: {where}: {message}")


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def make_event(event: str, slug: str, **fields: Any) -> dict[str, Any]:
    """Build a validated event with defaults filled in."""

    record = {key: copy.deepcopy(value) for key, value in DEFAULTS.items()}
    record["event"] = event
    record["slug"] = slug
    unknown = sorted(set(fields) - ALLOWED_FIELDS)
    if unknown:
        raise _error("event", f"unknown field(s): {', '.join(unknown)}")
    record.update({key: value for key, value in fields.items() if value is not None})
    if event == "start" and not record["status"]:
        record["status"] = "active"
    return validate_event(record)


def validate_event(record: Any) -> dict[str, Any]:
    """Validate and return an event without mutating the caller's object."""

    if not isinstance(record, dict):
        raise _error("event", "each JSONL line must be an object")
    if any(not isinstance(key, str) for key in record):
        raise _error("event", "field names must be strings")
    unknown = sorted(set(record) - ALLOWED_FIELDS)
    if unknown:
        raise _error("event", f"unknown field(s): {', '.join(unknown)}")
    if type(record.get("schema")) is not int or record["schema"] != SCHEMA:
        raise _error("schema", f"expected schema {SCHEMA}, got {record.get('schema')!r}")

    event = record.get("event")
    if event not in EVENTS:
        raise _error("event", f"event must be one of {', '.join(EVENTS)}")

    slug = record.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise _error("event", "slug must be lowercase letters, digits and hyphens")

    for field in _STRING_FIELDS:
        if not isinstance(record.get(field), str):
            raise _error(slug, f"{field} must be a string")
    for field in _LIST_FIELDS:
        if not _is_string_list(record.get(field)):
            raise _error(slug, f"{field} must be a list of non-empty strings")

    record_id = record["id"]
    if record_id and not ID_RE.fullmatch(record_id):
        raise _error(slug, "id must match fN with a non-negative sequence number")

    status = record["status"]
    if status:
        if status in TERMINAL_STATES:
            raise _error(slug, f"status {status!r} arrives through its event, never declared")
        if status not in STATUSES:
            raise _error(slug, f"status must be one of {', '.join(STATUSES)}")

    if event == "start":
        if not record["text"].strip():
            raise _error(slug, "start requires text")
        if not record["paths"]:
            raise _error(slug, "start requires at least one path in paths")
    if event in ("note", "abandon") and not record["text"].strip():
        raise _error(slug, f"{event} requires text")

    return record


__all__ = [
    "ALLOWED_FIELDS",
    "EVENTS",
    "ID_RE",
    "SCHEMA",
    "SLUG_RE",
    "STATUSES",
    "TERMINAL_STATES",
    "FeatureError",
    "make_event",
    "validate_event",
]
