"""Argparse wiring for the feature command group.

Split from docket.cli.feature to keep that file under the 300 line limit. The
handlers live there; this file only declares the flags that reach them.
"""

from __future__ import annotations

from docket import features
from docket.cli.feature import (
    cmd_feature_abandon,
    cmd_feature_amend,
    cmd_feature_done,
    cmd_feature_list,
    cmd_feature_note,
    cmd_feature_show,
    cmd_feature_start,
)
from docket.cli.feature_admin import cmd_feature_gc, cmd_feature_remap
from docket.cli.feature_render import cmd_feature_brief


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
    am.add_argument(
        "--clear",
        action="append",
        default=[],
        choices=features.CLEARABLE,
        metavar="FIELD",
        help=f"empty a declared list: {', '.join(features.CLEARABLE)}",
    )
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


__all__ = ["add_feature_parser"]
