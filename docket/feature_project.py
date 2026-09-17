"""Fold feature events into current state.

Split from docket.features because the schema, validation, store and
projection together crossed the 300-line limit.
"""

from __future__ import annotations

import copy
from typing import Any

from docket.features import TERMINAL_STATES, FeatureError

_CARRIED = ("text", "paths", "intends", "include", "exclude", "status")


def _error(where: str, message: str) -> FeatureError:
    return FeatureError(f"docket: {where}: {message}")


def project(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold events into one record per feature, newest run of a slug last.

    A slug is a ref: unique among open features, reusable after a close. The
    id is the permanent address, so a closed run keeps its own entry.
    """

    features_by_key: dict[str, dict[str, Any]] = {}
    open_key: dict[str, str] = {}
    order: list[str] = []

    for event in events:
        slug, verb = event["slug"], event["event"]
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
                **{field: copy.deepcopy(event[field]) for field in _CARRIED},
            }
            continue

        key = open_key.get(slug)
        if key is None:
            raise _error(slug, f"{verb} arrived with no open feature; it is closed or missing")
        feature = features_by_key[key]

        if verb == "amend":
            for field in _CARRIED:
                if event[field]:
                    feature[field] = copy.deepcopy(event[field])
            feature["state"] = feature["status"] or "active"
        elif verb == "note":
            feature["log"].append({"id": event["id"], "ts": event["ts"], "text": event["text"]})
        elif verb == "done":
            feature["state"] = "done"
            for field in ("intentional", "unintentional", "renamed_out"):
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


__all__ = ["project", "resolve"]
