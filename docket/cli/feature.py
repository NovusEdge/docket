"""Argparse wiring for the feature command group.

Logic lives in docket.features and docket.feature_outcome.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

from docket import env, feature_project, features
from docket.cli.feature_admin import archived, cmd_feature_gc, cmd_feature_remap
from docket.cli.feature_render import cmd_feature_brief


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def record_event(event: str, slug: str, **fields: Any) -> dict[str, Any]:
    return features.make_event(
        event,
        slug,
        ts=_now(),
        author=env.resolved_author(),
        session=env.session_id(),
        **fields,
    )


def _current(path) -> list[dict[str, Any]]:
    return feature_project.project(features.read(path))


def cmd_feature_start(args) -> int:
    path = env.features_path()
    root = env.project_root()
    from docket.feature_outcome import fork_point

    base, warning = fork_point(root)
    if warning:
        print(f"docket: {warning}", file=sys.stderr)
    current = _current(path)
    for existing in current:
        if existing["slug"] == args.slug and existing["state"] not in features.TERMINAL_STATES:
            print(f"docket: {args.slug}: a feature with this slug is already open", file=sys.stderr)
            return 1
    branch = env.branch(root)
    if branch:
        others = [
            f["slug"]
            for f in current
            if f["branch"] == branch and f["state"] not in features.TERMINAL_STATES
        ]
        if others:
            print(
                f"docket: {branch} already carries an active feature: {', '.join(others)}",
                file=sys.stderr,
            )
            return 1
    event = record_event(
        "start",
        args.slug,
        text=args.text,
        paths=args.path,
        intends=args.intends,
        base=base,
        branch=branch,
    )
    written = features.append(path, event)
    print(f"{written['id']} {args.slug}")
    return 0


def cmd_feature_list(args) -> int:
    from docket import feature_brief

    current = feature_brief.with_blocked(_current(env.features_path()), env.project_root())
    if args.state:
        current = [f for f in current if f["state"] == args.state]
    if args.json:
        print(json.dumps(current, ensure_ascii=False, indent=2))
        return 0
    for feature in current:
        if args.oneline:
            print(f"{feature['id']} {feature['slug']}")
        else:
            print(
                f"{feature['id']:<5} {feature['state']:<10} {feature['slug']:<24} {feature['text']}"
            )
    return 0


def cmd_feature_show(args) -> int:
    from docket import feature_brief

    path = env.features_path()
    current = feature_brief.with_blocked(_current(path), env.project_root())
    try:
        feature = feature_project.resolve(current, args.name)
    except features.FeatureError:
        feature = feature_project.resolve(archived(path), args.name)
    if args.json:
        print(json.dumps(feature, ensure_ascii=False, indent=2))
        return 0
    print(f"{feature['id']} {feature['slug']} [{feature['state']}]")
    print(f"  {feature['text']}")
    for label in ("paths", "intends", "intentional", "unintentional"):
        for value in feature[label]:
            print(f"  {label}: {value}")
    if feature.get("blocked_by"):
        print(f"  blocked_by: {', '.join(feature['blocked_by'])}")
    for note in feature["log"]:
        print(f"  note {note['ts']}: {note['text']}")
    return 0


def cmd_feature_note(args) -> int:
    path = env.features_path()
    feature_project.resolve(_current(path), args.slug)
    features.append(path, record_event("note", args.slug, text=args.text))
    return 0


def cmd_feature_amend(args) -> int:
    path = env.features_path()
    feature = feature_project.resolve(_current(path), args.slug)
    if feature["state"] in features.TERMINAL_STATES:
        print(f"docket: {args.slug}: feature is closed", file=sys.stderr)
        return 1
    fields = {
        key: value
        for key, value in (
            ("status", args.status),
            ("paths", args.path),
            ("intends", args.intends),
            ("include", _csv(args.include)),
            ("exclude", _csv(args.exclude)),
        )
        if value
    }
    if not fields:
        print("docket: amend needs at least one field to change", file=sys.stderr)
        return 1
    features.append(path, record_event("amend", args.slug, **fields))
    return 0


def cmd_feature_done(args) -> int:
    from docket.feature_outcome import changed_files, classify, is_dirty

    path = env.features_path()
    root = env.project_root()
    current = _current(path)
    feature = feature_project.resolve(current, args.slug)
    if feature["state"] in features.TERMINAL_STATES:
        print(f"docket: {args.slug}: feature is already closed", file=sys.stderr)
        return 1
    if is_dirty(root):
        print(
            "docket: the working tree has uncommitted changes; "
            "the change set reads committed history only",
            file=sys.stderr,
        )
        return 1

    from docket import feature_outcome, ledger

    changed, renames = changed_files(root, feature["base"])
    intentional, unintentional = classify(feature["paths"], changed)
    renamed_out = [
        f"{old} -> {new}"
        for old, new in renames
        if classify(feature["paths"], [old])[0] and not classify(feature["paths"], [new])[0]
    ]

    entries = ledger.project(ledger.read(env.ledger_path()), validated=True)
    realized = intentional + unintentional
    held_in, failed_in = _csv(args.held), _csv(args.failed)
    claims, held, failed, unanswered = feature_outcome.verify_claims(
        entries, realized, held_in, failed_in
    )
    if stray := feature_outcome.unattached_verdicts(claims, held_in, failed_in):
        print(
            f"docket: {', '.join(stray)} named a verdict but the change set did not "
            "touch it; no verdict recorded",
            file=sys.stderr,
        )

    features.append(
        path,
        record_event(
            "done",
            args.slug,
            intentional=intentional,
            unintentional=unintentional,
            renamed_out=renamed_out,
            held=held,
            failed=failed,
            unanswered=unanswered,
        ),
    )
    print(f"{feature['id']} done: {len(intentional)} intentional, {len(unintentional)} outside")
    for item in unintentional:
        print(f"  outside declared paths: {item}")

    by_id = {e["id"]: e for e in entries}
    report = feature_outcome.verification_report(
        by_id, claims, held, failed, features.qualified(feature)
    ) + feature_outcome.overlap_report(current, feature["id"], realized, features.TERMINAL_STATES)
    for line in report:
        print(line)
    return 0


def cmd_feature_abandon(args) -> int:
    path = env.features_path()
    feature = feature_project.resolve(_current(path), args.slug)
    if feature["state"] in features.TERMINAL_STATES:
        print(f"docket: {args.slug}: feature is already closed", file=sys.stderr)
        return 1
    features.append(path, record_event("abandon", args.slug, text=args.text))
    return 0


def add_feature_parser(sub) -> None:
    fe = sub.add_parser("feature", help="track a piece of work in flight")
    verbs = fe.add_subparsers(
        dest="feature_cmd",
        metavar="{start,list,show,note,amend,done,abandon,brief,remap,gc}",
    )

    st = verbs.add_parser("start", help="declare a piece of work")
    st.add_argument("slug")
    st.add_argument("--text", required=True)
    st.add_argument("--path", action="append", default=[], required=True)
    st.add_argument("--intends", action="append", default=[])
    st.set_defaults(func=cmd_feature_start)

    ls = verbs.add_parser("list", help="list features")
    # "blocked" is projected, never declared, so STATUSES omits it.
    ls.add_argument("--state", choices=(*features.STATUSES, "blocked", *features.TERMINAL_STATES))
    ls.add_argument("--oneline", action="store_true", help="id and slug only")
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
    am.add_argument("--include", default="", metavar="CSV")
    am.add_argument("--exclude", default="", metavar="CSV")
    am.set_defaults(func=cmd_feature_amend)

    dn = verbs.add_parser("done", help="close a feature and record what it changed")
    dn.add_argument("slug")
    dn.add_argument("--held", default="", metavar="CSV")
    dn.add_argument("--failed", default="", metavar="CSV")
    dn.set_defaults(func=cmd_feature_done)

    ab = verbs.add_parser("abandon", help="close a feature without a change set")
    ab.add_argument("slug")
    ab.add_argument("--text", required=True)
    ab.set_defaults(func=cmd_feature_abandon)

    br = verbs.add_parser("brief", help="print the ledger records governing a feature")
    br.add_argument("name", nargs="?", default="", metavar="SLUG_OR_ID")
    br.set_defaults(func=cmd_feature_brief)

    rm = verbs.add_parser("remap", help="repoint include and exclude lists through an id map")
    rm.add_argument(
        "mapfile", help="JSON object of old id to new id, from 'docket rebase --emit-map'"
    )
    rm.set_defaults(func=cmd_feature_remap)

    gc = verbs.add_parser("gc", help="archive closed features")
    gc.add_argument(
        "--expire",
        type=int,
        default=0,
        metavar="DAYS",
        help="only archive features closed more than DAYS ago",
    )
    gc.set_defaults(func=cmd_feature_gc)
