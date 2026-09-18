"""An append-only record of work in flight, kept beside the decision ledger.

The ledger records what was settled. This file records what is underway: a
named piece of work, the paths it declares, the outcomes it intends, and the
change set it realized. Nothing here reads or writes a ledger record.

Every line is an event. Current state is a projection over them.
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

from docket.ledger import ledger_lock

SCHEMA = 1
EVENTS = ("start", "amend", "note", "done", "abandon")
STATUSES = ("active", "paused", "review")
TERMINAL_STATES = ("done", "abandoned")
# paths is absent on purpose: start requires at least one, so a feature with
# none declares a blast radius it can never realize.
CLEARABLE = ("include", "exclude", "intends")

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
    "cleared": [],
    "base": "",
    "branch": "",
    "ts": "",
    "session": "",
    "author": "",
    "intentional": [],
    "unintentional": [],
    "renamed_out": [],
    "held": [],
    "failed": [],
    "unanswered": [],
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
    "cleared",
    "intentional",
    "unintentional",
    "renamed_out",
    "held",
    "failed",
    "unanswered",
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
    # A field the schema gained after a store was written is absent from every
    # line already in it, and every field below is required. schema is left out
    # of the fill so a line that declares no version still fails the next
    # check. A field that is present but the wrong type still fails.
    record = {
        **{key: copy.deepcopy(value) for key, value in DEFAULTS.items() if key != "schema"},
        **record,
    }
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

    for scope in record["paths"]:
        if "/" not in scope and not any(mark in scope for mark in "*?[]"):
            raise _error(
                slug,
                f"path {scope!r} can never match: the scope matcher skips a bare word "
                "with no directory separator and no glob character. Write a directory "
                "as 'name/**'",
            )

    if record["cleared"]:
        if event != "amend":
            raise _error(slug, f"cleared belongs to amend, not {event}")
        for field in record["cleared"]:
            if field not in CLEARABLE:
                raise _error(
                    slug, f"cannot clear {field!r}; clearable fields are {', '.join(CLEARABLE)}"
                )

    if event == "start":
        if not record["text"].strip():
            raise _error(slug, "start requires text")
        if not record["paths"]:
            raise _error(slug, "start requires at least one path in paths")
    if event in ("note", "abandon") and not record["text"].strip():
        raise _error(slug, f"{event} requires text")

    return record


def next_id(events: list[dict[str, Any]], floor: int = 0) -> str:
    """Allocate the next sequence number, local to this file.

    ``floor`` carries the highest id an archive holds, which the live store no
    longer shows.
    """
    numbers = [floor]
    for event in events:
        match = ID_RE.fullmatch(str(event.get("id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return "f" + str(max(numbers) + 1)


def qualified(event: dict[str, Any]) -> str:
    """The disambiguating form, used when a union merge leaves two of one ID.

    Short form first, the way git abbreviates a SHA until it is ambiguous.
    """
    base = str(event.get("base", ""))
    return f"{event['id']}@{base[:8]}" if base else str(event["id"])


def read(path: Path | str, lock: bool = True) -> list[dict[str, Any]]:
    """Read and strictly validate the store, raising on corruption."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        if lock:
            with ledger_lock(path, exclusive=False):
                text = path.read_text(encoding="utf-8")
        else:
            text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise _error("read", f"cannot read {path}: {exc}") from exc

    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _error(f"line {line_number}", f"invalid JSON: {exc.msg}") from exc
        try:
            events.append(validate_event(value))
        except FeatureError as exc:
            raise _error(f"line {line_number}", str(exc).removeprefix("docket: ")) from exc
    return events


def append(path: Path | str, record: dict[str, Any]) -> dict[str, Any]:
    """Validate and append one event under the ledger's locking mechanism.

    The lock file is this store's own, beside this path. Only the mechanism is
    shared with the ledger.
    """
    # Imported here, not at module scope: feature_project imports this module
    # for FeatureError and TERMINAL_STATES, and a module-level import back
    # makes docket.feature_project unimportable on its own.
    from docket.feature_archive import highest_archived_id
    from docket.feature_project import project

    path = Path(path)
    with ledger_lock(path):
        events = read(path, lock=False)
        candidate = copy.deepcopy(record)
        if not candidate.get("id"):
            # The archive holds ids the live store no longer carries. Counting
            # from the live store alone hands f1 out again after a gc, and
            # every recorded citation to the archived f1 retargets in silence.
            candidate["id"] = next_id(events, floor=highest_archived_id(path))
        candidate = validate_event(candidate)
        project(events + [candidate])
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(candidate, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise _error("append", f"cannot write {path}: {exc}") from exc
    return candidate


__all__ = [
    "ALLOWED_FIELDS",
    "CLEARABLE",
    "EVENTS",
    "ID_RE",
    "SCHEMA",
    "SLUG_RE",
    "STATUSES",
    "TERMINAL_STATES",
    "FeatureError",
    "append",
    "make_event",
    "next_id",
    "qualified",
    "read",
    "validate_event",
]
