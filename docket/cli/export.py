"""`docket export`: the relation graph as mermaid, graphviz DOT or Gephi CSV.

The renderers live in docket.graph_export; this module owns the argument
checks, the selection and where the output goes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docket import where
from docket.cli.graph import _graph_entries


def _write_csv(entries: list[dict], args: argparse.Namespace, superseded: bool) -> int:
    from docket.graph_export import to_csv

    nodes, edges = to_csv(entries, detail=args.detail, superseded=superseded)
    if not nodes:
        print("docket: no record in this selection carries a relation", file=sys.stderr)
        return 0
    out = Path(args.out)
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "nodes.csv").write_text(nodes, encoding="utf-8")
        (out / "edges.csv").write_text(edges, encoding="utf-8")
    except OSError as exc:
        print(f"docket: cannot write to {out}: {exc}", file=sys.stderr)
        return 1
    print(f"docket: wrote {out / 'nodes.csv'} and {out / 'edges.csv'}")
    print(
        "Gephi: File > Import spreadsheet, nodes.csv as a node table, then edges.csv as an edge table"
    )
    return 0


def selection(args: argparse.Namespace) -> tuple[list[dict], list[dict], bool]:
    query = where.parse(getattr(args, "where", None) or "")
    entries, _ = _graph_entries(args)
    shown = [e for e in entries if query.matches(e)]
    return entries, shown, bool(getattr(args, "superseded", False)) or query.wants_retired


def cmd_export(args: argparse.Namespace) -> int:
    if args.out and args.format != "csv":
        print("docket: --out belongs to --format csv", file=sys.stderr)
        return 2
    if args.format == "csv" and not args.out:
        # Gephi imports a node table and an edge table separately, so csv is
        # two documents and stdout cannot carry both.
        print("docket: --format csv writes two files; name a directory with --out", file=sys.stderr)
        return 2
    entries, shown, superseded = selection(args)
    if not entries:
        print("docket: nothing recorded")
        return 0

    if args.format == "csv":
        return _write_csv(shown, args, superseded)
    from docket.graph_export import to_dot, to_mermaid

    render = to_dot if args.format == "dot" else to_mermaid
    text = render(shown, detail=args.detail, direction=args.direction, superseded=superseded)
    if not text:
        print("docket: no record in this selection carries a relation", file=sys.stderr)
        return 0
    print(text)
    return 0
