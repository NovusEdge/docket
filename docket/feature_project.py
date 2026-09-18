"""Fold feature events into current state.

A slug is a ref and an id is the permanent address, so one slug can own
several entries here: at most one open, plus every closed run that reused the
name.
"""

from __future__ import annotations

import copy
from typing import Any

from docket.features import TERMINAL_STATES, FeatureError

_CARRIED = ("text", "paths", "intends", "include", "exclude", "status")


def _error(where: str, message: str) -> FeatureError:
    return FeatureError(f"docket: {where}: {message}")


def duplicate_ids(events: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    """Ids carried by more than one event, with the slugs that carry them.

    Reads the raw event list, so a caller can report a union merge's
    collisions without going through project(), which refuses that store.
    """

    seen: dict[str, list[str]] = {}
    for event in events:
        seen.setdefault(event["id"], []).append(event["slug"])
    return [(ident, slugs) for ident, slugs in seen.items() if len(slugs) > 1]


def project(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold events into one record per feature, newest run of a slug last.

    A slug is a ref: unique among open features, reusable after a close. The
    id is the permanent address, so a closed run keeps its own entry.
    """

    features_by_key: dict[str, dict[str, Any]] = {}
    open_key: dict[str, str] = {}
    order: list[str] = []
    seen_ids: dict[str, str] = {}

    for event in events:
        slug, verb = event["slug"], event["event"]
        # Two events sharing an id would overwrite each other in features_by_key,
        # losing one feature and duplicating the survivor. A union merge of two
        # branches produces exactly this, so it is a normal input, not corruption
        # that only a hand edit could cause.
        event_id = event["id"]
        if not event_id:
            raise _error(slug, f"{verb} carries no id")
        if event_id in seen_ids:
            raise _error(
                event_id,
                f"already used by {seen_ids[event_id]}; run 'docket feature remap'",
            )
        seen_ids[event_id] = slug

        if verb == "start":
            if slug in open_key:
                raise _error(slug, "a feature with this slug is already open")
            key = event["id"]
            open_key[slug] = key
            order.append(key)
            features_by_key[key] = {
                "id": event["id"],
                "slug": slug,
                "state": event["status"] or "active",
                "base": event["base"],
                "branch": event["branch"],
                "log": [],
                "intentional": [],
                "unintentional": [],
                "renamed_out": [],
                "held": [],
                "failed": [],
                "unanswered": [],
                **{field: copy.deepcopy(event[field]) for field in _CARRIED},
            }
            continue

        key = open_key.get(slug)
        if key is None:
            raise _error(slug, f"{verb} arrived with no open feature; it is closed or missing")
        feature = features_by_key[key]

        if verb == "amend":
            # Clearing runs first, so an amend that both clears and sets one
            # field ends with the set value. An empty list cannot carry the
            # intent on its own: the loop below skips a falsy value, because
            # an amend names only the fields it changes.
            for field in event["cleared"]:
                feature[field] = []
            for field in _CARRIED:
                if event[field]:
                    feature[field] = copy.deepcopy(event[field])
            feature["state"] = feature["status"] or "active"
        elif verb == "note":
            feature["log"].append({"id": event["id"], "ts": event["ts"], "text": event["text"]})
        elif verb == "done":
            feature["state"] = "done"
            for field in (
                "intentional",
                "unintentional",
                "renamed_out",
                "held",
                "failed",
                "unanswered",
            ):
                feature[field] = copy.deepcopy(event[field])
            del open_key[slug]
        elif verb == "abandon":
            feature["state"] = "abandoned"
            feature["log"].append({"id": event["id"], "ts": event["ts"], "text": event["text"]})
            del open_key[slug]

    return [features_by_key[key] for key in order]


def resolve(features_list: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Find a feature by id, or by slug among the open ones."""

    for feature in features_list:
        if feature["id"] == name:
            return feature
    open_matches = [
        f for f in features_list if f["slug"] == name and f["state"] not in TERMINAL_STATES
    ]
    if len(open_matches) == 1:
        return open_matches[0]
    closed = [f["id"] for f in features_list if f["slug"] == name]
    if closed:
        raise _error(name, f"no open feature; closed runs are {', '.join(closed)}")
    raise _error(name, "no such feature")


def remap_changes(
    current: list[dict[str, Any]], mapping: dict[str, str]
) -> list[tuple[str, dict[str, list[str]]]]:
    """Open features whose include/exclude ids the mapping rewrites, and to what."""

    changes = []
    for feature in current:
        if feature["state"] in TERMINAL_STATES:
            continue
        fields = {}
        for field in ("include", "exclude"):
            remapped = [mapping.get(ident, ident) for ident in feature[field]]
            if remapped != feature[field]:
                fields[field] = remapped
        if fields:
            changes.append((feature["slug"], fields))
    return changes


__all__ = ["duplicate_ids", "project", "remap_changes", "resolve"]
