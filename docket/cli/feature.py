"""Argparse wiring and rendering for the feature command group.

Logic lives in docket.features and docket.feature_outcome. This module builds
records, prints them, and returns exit codes.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

from docket import env, features


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _record(event: str, slug: str, **fields: Any) -> dict[str, Any]:
    return features.make_event(
        event,
        slug,
        ts=_now(),
        author=env.resolved_author(),
        session=env.session_id(),
        **fields,
    )


def _current(path) -> list[dict[str, Any]]:
    return features.project(features.read(path))


def cmd_feature_start(args) -> int:
    path = env.features_path()
    root = env.project_root()
    from docket.feature_outcome import fork_point

    base, warning = fork_point(root)
    if warning:
        print(f"docket: {warning}", file=sys.stderr)
    # Checked before the append. project() raises on a duplicate open slug, but
    # only once the offending start is already a line in the file.
    for existing in _current(path):
        if existing["slug"] == args.slug and existing["state"] not in features.TERMINAL_STATES:
            print(f"docket: {args.slug}: a feature with this slug is already open", file=sys.stderr)
            return 1
    event = _record(
        "start",
        args.slug,
        text=args.text,
        paths=args.path,
        intends=args.intends,
        base=base,
        branch=env.branch(root),
    )
    written = features.append(path, event)
    print(f"{features.qualified(written)} {args.slug}")
    return 0


def cmd_feature_list(args) -> int:
    current = _current(env.features_path())
    if args.state:
        current = [f for f in current if f["state"] == args.state]
    if args.json:
        print(json.dumps(current, ensure_ascii=False, indent=2))
        return 0
    for feature in current:
        print(f"{feature['id']:<5} {feature['state']:<10} {feature['slug']:<24} {feature['text']}")
    return 0


def cmd_feature_show(args) -> int:
    feature = features.resolve(_current(env.features_path()), args.name)
    if args.json:
        print(json.dumps(feature, ensure_ascii=False, indent=2))
        return 0
    print(f"{feature['id']} {feature['slug']} [{feature['state']}]")
    print(f"  {feature['text']}")
    for label in ("paths", "intends", "intentional", "unintentional"):
        for value in feature[label]:
            print(f"  {label}: {value}")
    for note in feature["log"]:
        print(f"  note {note['ts']}: {note['text']}")
    return 0


def cmd_feature_note(args) -> int:
    path = env.features_path()
    features.resolve(_current(path), args.slug)
    features.append(path, _record("note", args.slug, text=args.text))
    return 0


def cmd_feature_amend(args) -> int:
    path = env.features_path()
    feature = features.resolve(_current(path), args.slug)
    if feature["state"] in features.TERMINAL_STATES:
        print(f"docket: {args.slug}: feature is closed", file=sys.stderr)
        return 1
    fields = {
        key: value
        for key, value in (
            ("status", args.status),
            ("paths", args.path),
            ("intends", args.intends),
        )
        if value
    }
    if not fields:
        print("docket: amend needs at least one field to change", file=sys.stderr)
        return 1
    features.append(path, _record("amend", args.slug, **fields))
    return 0


def add_feature_parser(sub) -> None:
    fe = sub.add_parser("feature", help="track a piece of work in flight")
    verbs = fe.add_subparsers(dest="feature_cmd", metavar="{start,list,show,note,amend}")

    st = verbs.add_parser("start", help="declare a piece of work")
    st.add_argument("slug")
    st.add_argument("--text", required=True)
    st.add_argument("--path", action="append", default=[], required=True)
    st.add_argument("--intends", action="append", default=[])
    st.set_defaults(func=cmd_feature_start)

    ls = verbs.add_parser("list", help="list features")
    ls.add_argument("--state", choices=(*features.STATUSES, *features.TERMINAL_STATES))
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_feature_list)

    sh = verbs.add_parser("show", help="print one feature")
    sh.add_argument("name", metavar="SLUG_OR_ID")
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_feature_show)

    nt = verbs.add_parser("note", help="append a dated line to a feature's log")
    nt.add_argument("slug")
    nt.add_argument("text")
    nt.set_defaults(func=cmd_feature_note)

    am = verbs.add_parser("amend", help="replace a declared field")
    am.add_argument("slug")
    am.add_argument("--status", choices=features.STATUSES)
    am.add_argument("--path", action="append", default=[])
    am.add_argument("--intends", action="append", default=[])
    am.set_defaults(func=cmd_feature_amend)
