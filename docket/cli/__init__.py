from __future__ import annotations

import argparse
import sys

from docket import features, version
from docket.cli.admin import (
    cmd_check,
    cmd_init,
    cmd_merge_driver,
    cmd_migrate,
    cmd_rebase,
)
from docket.cli.completion import cmd_completion
from docket.cli.construct import cmd_construct
from docket.cli.context_cmd import CONTEXT_ENVELOPES, cmd_context
from docket.cli.correct import add_correct_parser
from docket.cli.export import cmd_export
from docket.cli.feature_parser import add_feature_parser
from docket.cli.graph import cmd_graph
from docket.cli.query import cmd_filter_ids, cmd_list, cmd_show, cmd_where
from docket.cli.record import cmd_claim, cmd_decision, cmd_question
from docket.cli.review import add_review_parser
from docket.cli.selfupdate import cmd_update, cmd_update_fetch
from docket.cli.web import port_arg, web_conflict
from docket.ledger import KINDS, STATES, LedgerError
from docket.support import REASONS
from docket.where import WhereError


class VersionAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print(f"docket {version()}")
        parser.exit()


class HelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print(f"docket {version()}")
        print(parser.format_help(), end="")
        parser.exit()


def _add_shared_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--scope", action="append", default=[])
    p.add_argument("--rationale", default="")
    p.add_argument("--supports", action="append", default=[], metavar="CSV")
    p.add_argument("--depends-on", default="", metavar="CSV")
    p.add_argument("--answers", default="", metavar="CSV")
    p.add_argument("--supersedes", default="", metavar="CSV")
    p.add_argument("--supersede-reason", choices=REASONS, help="restate, revise or reverse")
    p.add_argument("--evidence", action="append", default=[])
    p.add_argument("--revisit", default="")
    p.add_argument("--cost", default="")
    p.add_argument("--pin", action="store_true")


def _add_filter_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--kind", choices=KINDS)
    p.add_argument(
        "--state", choices=tuple(sorted({state for values in STATES.values() for state in values}))
    )
    p.add_argument("--find", help="match question or answer text")
    p.add_argument("--where", metavar="QUERY", help="filter with the query language")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="docket",
        description="Record typed claims, decisions, and open questions.",
        add_help=False,
    )
    p.add_argument("-h", "--help", action=HelpAction, nargs=0, help="show this help and exit")
    p.add_argument("--version", action=VersionAction, nargs=0, help="print the release and exit")
    sub = p.add_subparsers(
        dest="cmd",
        metavar=(
            "{claim,decision,question,correct,review,list,show,graph,export,context,where,check,"
            "rebase,migrate,init,feature,completion,update}"
        ),
    )

    cl = sub.add_parser("claim", help="record a proposition")
    cl.add_argument("text")
    cl.add_argument("--state", choices=STATES["claim"], default="unassessed")
    _add_shared_args(cl)
    cl.set_defaults(func=cmd_claim)

    dec = sub.add_parser("decision", help="record a commitment")
    dec.add_argument("text", metavar="QUESTION")
    dec.add_argument("--choice", required=True)
    dec.add_argument("--alternative", action="append", default=[])
    dec.add_argument("--state", choices=STATES["decision"], default="adopted")
    dec.add_argument("--decided-by", default="")
    _add_shared_args(dec)
    dec.set_defaults(func=cmd_decision)

    qu = sub.add_parser("question", help="record an unresolved inquiry")
    qu.add_argument("text")
    _add_shared_args(qu)
    qu.set_defaults(func=cmd_question)

    add_correct_parser(sub)
    add_review_parser(sub)

    ls = sub.add_parser("list", help="list records")
    _add_filter_args(ls)
    ls.add_argument(
        "--superseded",
        action="store_true",
        help="include entries a later decision retired",
    )
    ls.add_argument("--oneline", action="store_true", help="one line per entry, no answer")
    ls.add_argument("--json", action="store_true", help="print projected records as JSON")
    ls.add_argument("--plain", action="store_true", help="force colour off")
    ls.add_argument("--pretty", action="store_true", help="force colour on, e.g. piping to less -R")
    ls.set_defaults(func=cmd_list)

    gr = sub.add_parser("graph", help="browse decision support relationships")
    gr.add_argument("--style", choices=("forest", "rail", "compact"))
    _add_filter_args(gr)
    gr.add_argument("--plain", action="store_true", help="force colour off")
    gr.add_argument("--pretty", action="store_true", help="force colour on, e.g. piping to less -R")
    mode = gr.add_mutually_exclusive_group()
    mode.add_argument(
        "--interactive", action="store_true", help="use the native interactive viewer"
    )
    mode.add_argument(
        "--no-interactive", action="store_true", help="force the static text renderer"
    )
    gr.add_argument("--web", action="store_true", help="serve the graph to a browser, live")
    gr.add_argument("--port", type=port_arg, help="port for --web, default 7347")
    gr.set_defaults(func=cmd_graph)

    ex = sub.add_parser("export", help="write the relation graph as mermaid, DOT or Gephi CSV")
    ex.add_argument("--format", choices=("mermaid", "dot", "csv"), default="mermaid")
    _add_filter_args(ex)
    ex.add_argument(
        "--superseded", action="store_true", help="include retired records and the retire edges"
    )
    ex.add_argument(
        "--out",
        metavar="DIR",
        help="directory for --format csv, which writes nodes.csv and edges.csv",
    )
    ex.add_argument(
        "--detail", type=int, default=40, help="characters of record text per node, 0 for ids only"
    )
    ex.add_argument(
        "--direction", choices=("LR", "TD", "RL", "BT"), default="LR", help="layout direction"
    )
    ex.set_defaults(func=cmd_export)

    sh = sub.add_parser("show", help="print one entry, human-readable")
    sh.add_argument("id")
    sh.add_argument("--json", action="store_true", help="print the entry as JSON")
    sh.add_argument("--at", default="", help="print the record as history stood at this record ID")
    sh.set_defaults(func=cmd_show)

    ctx = sub.add_parser("context", help="print the ledger for session injection")
    ctx.add_argument(
        "--for",
        dest="for_harness",
        choices=sorted(CONTEXT_ENVELOPES),
        help="wrap the ledger text in this harness's own hook envelope",
    )
    ctx.add_argument("--query", default="")
    ctx.add_argument("--file", action="append", default=[])
    # No default: the renderer treats None as a soft target that a
    # task-matching record may exceed. A value here is a hard ceiling.
    ctx.add_argument("--max-chars", type=int, default=None)
    ctx.add_argument("--all", dest="all_records", action="store_true")
    ctx.add_argument(
        "--auto-scope",
        dest="auto_scope",
        action="store_true",
        default=None,
        help="derive file scope from git, even alongside an explicit query or file",
    )
    ctx.add_argument(
        "--no-auto-scope",
        dest="auto_scope",
        action="store_false",
        help="never derive file scope from git",
    )
    ctx.add_argument(
        "--since", default="", help="report what changed after this record ID or ID@DIGEST"
    )
    ctx.set_defaults(func=cmd_context)

    wh = sub.add_parser("where", help="print which ledger file is in use")
    wh.set_defaults(func=cmd_where)

    ck = sub.add_parser("check", help="report what makes the ledger unreadable")
    ck.set_defaults(func=cmd_check)

    rb = sub.add_parser("rebase", help="renumber another ledger's tail onto this one")
    rb.add_argument("other", help="path to the other branch's ledger")
    rb.add_argument("--dry-run", action="store_true", help="print the ID map and write nothing")
    rb.add_argument("--emit-map", metavar="PATH", help="write the old-to-new id map as JSON")
    rb.set_defaults(func=cmd_rebase)

    # No help text and absent from the metavar list above: git calls this,
    # people do not.
    md = sub.add_parser("merge-driver")
    md.add_argument("base")
    md.add_argument("ours")
    md.add_argument("theirs")
    md.set_defaults(func=cmd_merge_driver)

    mg = sub.add_parser("migrate", help="convert a legacy ledger to the current schema")
    source = mg.add_mutually_exclusive_group()
    source.add_argument("--map", help="classification map to apply instead of the derived one")
    source.add_argument("--emit-map", help="write the derived map to this path and stop")
    mg.add_argument("--dry-run", action="store_true", help="report the conversion and stop")
    mg.set_defaults(func=cmd_migrate)

    it = sub.add_parser("init", help="move this project's ledger into the repository")
    it.set_defaults(func=cmd_init)

    cs = sub.add_parser("construct", help="stage ledger proposals from written history")
    cs.add_argument("paths", nargs="*", help="documents or directories to read")
    cs.add_argument(
        "--review", action="store_true", help="print staged proposals with their source anchors"
    )
    cs.add_argument("--accept", action="store_true", help="append accepted proposals to the ledger")
    cs.add_argument("--source", help="with --accept, take only this document's records")
    cs.add_argument("--jobs", type=int, default=8, help="concurrent extraction calls")
    cs.add_argument(
        "--exclude",
        action="append",
        metavar="DIR",
        default=[],
        help="also skip this directory name anywhere in a walk; repeat to add more",
    )
    cs.add_argument(
        "--no-exclude", action="store_true", help="read every directory, including archive"
    )
    cs.add_argument(
        "--untracked", action="store_true", help="also read documents git does not track"
    )
    cs.add_argument(
        "--dry-run", action="store_true", help="list the documents that would be read; call nothing"
    )
    # No choices=: the provider names live in docket.construct.client, and this
    # parser is built by the SessionStart hook on every session. The command
    # body validates instead.
    cs.add_argument(
        "--install-sdk", metavar="PROVIDER", help="install the SDK this provider needs, then exit"
    )
    cs.add_argument(
        "--remove-sdk", action="store_true", help="delete the SDK virtualenv, then exit"
    )
    cs.set_defaults(func=cmd_construct)

    add_feature_parser(sub)

    co = sub.add_parser("completion", help="print a shell completion script")
    co.add_argument("shell", choices=("bash", "zsh", "fish"))
    co.set_defaults(func=cmd_completion)

    ud = sub.add_parser("update", help="update this Docket installation")
    ud.add_argument(
        "--check", action="store_true", help="report whether an update is available; change nothing"
    )
    ud.set_defaults(func=cmd_update)

    sub.add_parser("_update-fetch").set_defaults(func=cmd_update_fetch)

    fi = sub.add_parser("_filter-ids")
    fi.add_argument("query", nargs=argparse.REMAINDER)
    fi.set_defaults(func=cmd_filter_ids)

    args = p.parse_args(argv)
    if args.cmd is None:
        print(f"docket {version()}")
        print(p.format_help(), end="")
        return 0
    if args.cmd == "graph" and (flag := web_conflict(args)):
        p.error(f"graph --web conflicts with {flag}")
    if args.cmd == "graph" and args.interactive:
        if args.plain:
            p.error("graph --interactive conflicts with --plain")
        if args.style is not None:
            p.error("graph --interactive conflicts with --style")
    if args.cmd == "feature" and getattr(args, "feature_cmd", None) is None:
        p.error("feature needs a subcommand")
    from docket.feature_outcome import OutcomeError

    try:
        return args.func(args)
    except (LedgerError, features.FeatureError, OutcomeError, WhereError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
