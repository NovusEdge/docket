"""Commands that print records a person asked for: list, show, where.

docket context assembles a whole briefing under a budget and lives in
docket.cli.context_cmd, which keeps this file under the 300 line limit.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import textwrap

from docket import corrections, env
from docket.cli.term import _DIM, _STATE_COLOR, _c, _match, _use_color
from docket.context_model import positions
from docket.env import LEDGER, justification_sets, read, retired_by
from docket.ledger import project

_LIST_ID_W, _LIST_STATE_W = 5, 9
_LIST_HEAD_W = _LIST_ID_W + 1 + _LIST_STATE_W + 1  # clears the id+state columns


def _list_dim_tail(line: str, marker: str, use_color: bool) -> str:
    """Dim a line from `marker` onward, if the line carries it at all.

    Wrapping can split the marker onto a line of its own or leave it whole;
    either way the dim colour must start where the marker starts, not at
    column 0.
    """
    idx = line.find(marker)
    if idx == -1 or not use_color:
        return line
    return line[:idx] + _c(_DIM, line[idx:], use_color)


def cmd_list(args: argparse.Namespace) -> int:
    entries = project(read(env.ledger_path()), validated=True)
    retired = retired_by(entries)
    if not args.superseded:
        entries = [e for e in entries if e.get("id") not in retired]
    if args.state:
        entries = [e for e in entries if e.get("state") == args.state]
    if getattr(args, "kind", None):
        entries = [e for e in entries if e.get("kind") == args.kind]
    if args.find:
        entries = [e for e in entries if _match(e, args.find)]
    if not entries:
        if getattr(args, "json", False):
            print("[]")
            return 0
        print("docket: nothing recorded")
        return 0
    if getattr(args, "json", False):
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0

    use_color = False if args.plain else True if args.pretty else _use_color()
    width = shutil.get_terminal_size().columns

    if args.oneline:
        for e in entries:
            id_str = _c(_STATE_COLOR.get(e["state"], _DIM), f"{e['id']:<{_LIST_ID_W}}", use_color)
            # Truncated, never wrapped: one entry stays one line, which is what
            # makes the mode scannable and pipeable into grep.
            room = max(width - _LIST_ID_W - _LIST_STATE_W - 2, 20)
            question = textwrap.shorten(e["text"], width=room, placeholder="...")
            print(f"{id_str} {e['state']:<{_LIST_STATE_W}} {question}")
        return 0

    for e in entries:
        sets = justification_sets(e)
        # " | " separates alternatives; each alternative's own ids stay comma-joined.
        dep = f"  <- {' | '.join(','.join(s) for s in sets)}" if sets else ""
        gone = f"  (superseded by {retired[e['id']]})" if e.get("id") in retired else ""

        id_str = _c(_STATE_COLOR.get(e["state"], _DIM), f"{e['id']:<{_LIST_ID_W}}", use_color)
        state_str = _c(
            _STATE_COLOR.get(e["state"], _DIM), f"{e['state']:<{_LIST_STATE_W}}", use_color
        )

        avail = max(width - _LIST_HEAD_W, 20)
        wrapped = textwrap.wrap(e["text"] + dep + gone, width=avail) or [""]
        print(
            f"{id_str} {state_str} "
            + _list_dim_tail(
                _list_dim_tail(wrapped[0], "<-", use_color), "(superseded by", use_color
            )
        )
        for line in wrapped[1:]:
            line = _list_dim_tail(
                _list_dim_tail(line, "<-", use_color), "(superseded by", use_color
            )
            print(" " * _LIST_HEAD_W + line)

        detail = e.get("choice", e.get("rationale", ""))
        if detail:
            for line in textwrap.wrap(detail, width=max(width - 6, 20)) or [""]:
                print("      " + line)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    raw = read(env.ledger_path())
    if args.at:
        if not any(item.get("id") == args.at for item in raw):
            print(f"docket: unknown record {args.at}", file=sys.stderr)
            return 1
        at = positions(raw)
        cutoff = at[args.at]
        raw = [item for item in raw if at[item["id"]] <= cutoff]
    if corrections.split_id(args.id):
        return _show_correction(raw, args.id, args.json)
    entries = project(raw, validated=True)
    by_id = {e.get("id"): e for e in entries}
    e = by_id.get(args.id)
    if not e:
        print(f"docket: no entry {args.id}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(e, indent=2))
        return 0

    def cite(i: str) -> str:
        q = by_id.get(i, {}).get("text")
        return f"{i} ({q})" if q else i

    width = shutil.get_terminal_size().columns

    def field(label: str, value: str) -> None:
        """One labelled field, wrapped under a hanging indent past the label."""
        indent = " " * (len(label) + 4)
        for i, line in enumerate(
            textwrap.wrap(f"  {label}: {value}", width=width, subsequent_indent=indent)
            or [f"  {label}:"]
        ):
            print(line)

    for line in textwrap.wrap(
        f"{e['id']}  {e.get('kind', '')}  {e.get('state', '')}  {e.get('text', '')}",
        width=width,
        subsequent_indent=" " * 15,
    ):
        print(line)
    field("Choice", e.get("choice", ""))
    field("Rationale", e.get("rationale", ""))
    sets = justification_sets(e)
    if sets:
        field("Because", " | ".join(", ".join(cite(i) for i in s) for s in sets))
    supersedes = e.get("supersedes") or []
    if supersedes:
        field("Supersedes", ", ".join(cite(i) for i in supersedes))
    retired = retired_by(entries)
    if e["id"] in retired:
        field("Superseded by", cite(retired[e["id"]]))
    if e.get("depends_on"):
        field("Depends on", ", ".join(cite(i) for i in e["depends_on"]))
    if e.get("answers"):
        field("Answers", ", ".join(cite(i) for i in e["answers"]))
    if e.get("resolved_by"):
        field("Resolved by", ", ".join(cite(i) for i in e["resolved_by"]))
    if e.get("decided_by"):
        field("Decided by", e["decided_by"])
    if e.get("cost_if_wrong"):
        field("Cost if wrong", e["cost_if_wrong"])
    if e.get("corrections"):
        field("Corrections", ", ".join(e["corrections"]))
    field("Recorded state", e.get("recorded_state", e.get("state", "")))
    print(f"  Recorded: {e.get('ts', '')}")
    print(
        f"  Author: {e.get('author', '')}  Session: {e.get('session', '')}  Branch: {e.get('branch', '')}"
    )
    return 0


def _show_correction(raw: list, ident: str, as_json: bool) -> int:
    at = next((index for index, item in enumerate(raw) if item["id"] == ident), None)
    if at is None:
        print(f"docket: no entry {ident}", file=sys.stderr)
        return 1
    line = raw[at]
    target = next(i for i in corrections.fold(raw[:at]) if i["id"] == line["corrects"])
    before = {field: target.get(field) for field in line["fields"]}
    if as_json:
        print(json.dumps({**line, "before": before}, indent=2))
        return 0
    print(f"{ident}  correction  corrects {line['corrects']}")
    for field, value in line["fields"].items():
        print(f"  {field}: {json.dumps(before[field])} -> {json.dumps(value)}")
    if line["reason"]:
        print(f"  Reason: {line['reason']}")
    print(
        f"  Author: {line['author']}  Session: {line['session']}  Branch: {line['branch']}  "
        f"Ts: {line['ts']}"
    )
    return 0


def cmd_where(args: argparse.Namespace) -> int:
    path = env.ledger_path()
    kind = "project" if LEDGER.name in str(path) and ".claude" not in str(path) else "global"
    print(f"{path}  ({kind}, {'exists' if path.exists() else 'not created yet'})")
    return 0


__all__ = ["cmd_list", "cmd_show", "cmd_where"]
