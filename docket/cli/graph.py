from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from docket import ROOT, env
from docket.cli.term import (
    _DIM,
    _GRAPH_GLYPHS,
    _GRAPH_GLYPHS_ASCII,
    _STATE_COLOR,
    _c,
    _match,
    _use_color,
    _use_glyphs,
)
from docket.context_model import positions
from docket.env import justification_sets, read, retired_by
from docket.ledger import graph_payload, project


def _node_info(e: dict, retired: dict[str, str]) -> dict:
    """Precompute what every graph renderer needs from one entry.

    supports is the union of ids across every alternative set, in first-seen
    order, so the forest can hang a node under its first support and name the
    rest as extras without walking justification_sets() again per renderer.
    """
    sets = justification_sets(e)
    supports: list[str] = []
    for s in sets:
        for i in s:
            if i not in supports:
                supports.append(i)
    return {
        "id": e["id"],
        "kind": e.get("kind", ""),
        "state": e.get("state", ""),
        "recorded_state": e.get("recorded_state", e.get("state", "")),
        "question": e.get("text", ""),
        "answer": e.get("choice", e.get("rationale", "")),
        "cost": e.get("cost_if_wrong", ""),
        "sets": sets,
        "supports": supports,
        "retired_by": retired.get(e["id"], ""),
        "supersedes": e.get("supersedes", []),
        "depends_on": e.get("depends_on", []),
        "answers": e.get("answers", []),
        "resolved_by": e.get("resolved_by", []),
        "scope": e.get("scope", []),
        "rationale": e.get("rationale", ""),
        "alternatives": e.get("alternatives", []),
        "evidence": e.get("evidence", []),
        "revisit": e.get("revisit", ""),
        "author": e.get("author", ""),
        "ts": e.get("ts", ""),
        "branch": e.get("branch", ""),
        "session": e.get("session", ""),
        "pinned": e.get("pinned", False),
        "applicable": e.get("applicable"),
        "blocked_by": e.get("blocked_by", []),
        "decided_by": e.get("decided_by", ""),
    }


def _formula(sets: list[list[str]]) -> str:
    return " | ".join(",".join(s) for s in sets)


def _blocked_text(info: dict) -> str:
    if info.get("kind") == "decision" and info.get("applicable") is False:
        return "! blocked by " + (", ".join(info.get("blocked_by", [])) or "prerequisites")
    return ""


def _graph_entries(args: argparse.Namespace) -> tuple[list[dict], dict[str, str]]:
    """Entries for `graph`, including retired ones.

    Unlike cmd_list, retired entries stay in, or the edges a later entry drew
    to them would dangle.
    """
    entries = project(read(env.ledger_path()), validated=True)
    retired = retired_by(entries)
    if args.state:
        entries = [e for e in entries if e.get("state") == args.state]
    if args.find:
        entries = [e for e in entries if _match(e, args.find)]
    if getattr(args, "kind", None):
        entries = [e for e in entries if e.get("kind") == args.kind]
    return entries, retired


def _graph_viewer_path() -> Path:
    """The viewer built by the installer in this checkout."""
    name = "docket-graph.exe" if os.name == "nt" else "docket-graph"
    return ROOT / "graph" / name


def _graph_is_tty() -> bool:
    """Whether graph owns both terminal handles needed by Bubble Tea."""
    return all(
        bool(getattr(stream, "isatty", lambda: False)()) for stream in (sys.stdin, sys.stdout)
    )


def _graph_viewer_error(viewer: Path) -> None:
    print(
        f"docket: interactive viewer not found at {viewer}; "
        "build it with `cd graph && go build -o docket-graph .`",
        file=sys.stderr,
    )


def _graph_payload(entries: list[dict], retired: dict[str, str]) -> dict:
    """Serialize only the normalized graph model consumed by the Go viewer."""
    return graph_payload(entries)


def _run_graph_viewer(entries: list[dict], retired: dict[str, str], pretty: bool = False) -> int:
    """Run the native viewer with an inherited terminal and private input."""
    viewer = _graph_viewer_path()
    temp_path: Path | None = None
    try:
        fd, raw_path = tempfile.mkstemp(prefix="docket-graph-", suffix=".json")
        temp_path = Path(raw_path)
        with os.fdopen(fd, "w", encoding="utf-8") as data_file:
            json.dump(_graph_payload(entries, retired), data_file)
            data_file.write("\n")

        try:
            command = [str(viewer), "--data", str(temp_path)]
            if pretty:
                command.append("--pretty")
            result = subprocess.run(command)
        except KeyboardInterrupt:
            return 130
        except OSError as exc:
            print(f"docket: could not start interactive viewer: {exc}", file=sys.stderr)
            return 1
        return result.returncode
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def _state_glyph(state: str, glyphs: dict, use_color: bool) -> str:
    g = glyphs["open"] if state == "open" else glyphs["bullet"]
    return _c(_STATE_COLOR.get(state, _DIM), g, use_color)


def _label(info: dict, glyphs: dict, use_color: bool) -> tuple[str, int]:
    """The `glyph id  state ` prefix shared by forest and compact rows, plus
    its printable width (ANSI codes have zero display width, so the width is
    computed from an uncoloured copy rather than len() on the coloured one)."""
    rest = f"{info['id']:<4}{info['state']:<11}"
    plain_glyph = glyphs["open"] if info["state"] == "open" else glyphs["bullet"]
    plain = f"{plain_glyph} {rest}"
    colored = f"{_state_glyph(info['state'], glyphs, use_color)} {rest}"
    return colored, len(plain)


def _id_state(info: dict) -> str:
    """id + state with no glyph, for the rail: the glyph already sits in the
    lane at the node's own column, so repeating it in the label would double it."""
    return f"{info['id']:<4}{info['state']:<11}"


def _forest_roots(entries: list[dict], nodes: dict[str, dict], at: dict[str, int]) -> list[str]:
    """Entries nothing supports. A support the graph filtered out (--state,
    --find) also makes its dependent a root: there is nothing to hang it under."""
    visible = set(nodes)
    roots = [
        e["id"]
        for e in entries
        if not nodes[e["id"]]["supports"] or not (set(nodes[e["id"]]["supports"]) & visible)
    ]
    return sorted(roots, key=lambda eid: at[eid], reverse=True)


def _forest_children(
    entries: list[dict], nodes: dict[str, dict], roots: list[str], at: dict[str, int]
) -> dict[str, list[str]]:
    """Map each support id to the children hung under it (its primary support
    only; extras are named in text, never drawn, so each node has one parent)."""
    children: dict[str, list[str]] = {}
    roots_set = set(roots)
    for e in sorted(entries, key=lambda e: at[e["id"]]):
        eid = e["id"]
        if eid in roots_set:
            continue
        supports = [s for s in nodes[eid]["supports"] if s in nodes]
        if not supports:
            continue
        children.setdefault(supports[0], []).append(eid)
    return children


def _forest_lines(
    nodes: dict[str, dict],
    roots: list[str],
    children: dict[str, list[str]],
    glyphs: dict,
    use_color: bool,
    width: int,
    at: dict[str, int],
) -> list[str]:
    lines: list[str] = []

    def walk(eid: str, ancestor_last: list[bool]) -> None:
        info = nodes[eid]
        prefix = "".join(("   " if last else glyphs["vert"] + "  ") for last in ancestor_last[:-1])
        if ancestor_last:
            prefix += glyphs["elbow"] if ancestor_last[-1] else glyphs["tee"]
        label, label_width = _label(info, glyphs, use_color)

        extras = info["supports"][1:]
        text = info["question"]
        if extras:
            text += "  (also <- %s)" % ", ".join(extras)
        if len(info["sets"]) > 1:
            text += "\n" + _formula(info["sets"])
        if info["retired_by"]:
            text += "\n" + _c(
                _DIM, f"{glyphs['retired']} retired by {info['retired_by']}", use_color
            )
        # The answer is what separates forest from compact; compact is the
        # one-line view.
        text += "\n" + info["answer"]
        if info["cost"]:
            text += "\n" + "! cost: " + info["cost"]
        if _blocked_text(info):
            text += "\n" + _blocked_text(info)

        cont_prefix = "".join(("   " if last else glyphs["vert"] + "  ") for last in ancestor_last)
        avail = max(width - len(prefix) - label_width, 20)
        wrapped_lines: list[str] = []
        for para in text.split("\n"):
            wrapped_lines.extend(textwrap.wrap(para, width=avail) or [""])

        lines.append(prefix + label + " " + wrapped_lines[0])
        for extra_line in wrapped_lines[1:]:
            lines.append(cont_prefix + " " * label_width + " " + extra_line)

        kids = sorted(children.get(eid, []), key=lambda eid: at[eid])
        for i, kid in enumerate(kids):
            walk(kid, ancestor_last + [i == len(kids) - 1])

    # A root has no parent, so it carries no connector. Passing a depth here
    # drew every root as a child of something invisible.
    for r in roots:
        walk(r, [])
    return lines


def _compact_lines(
    nodes: dict[str, dict],
    roots: list[str],
    children: dict[str, list[str]],
    glyphs: dict,
    use_color: bool,
    at: dict[str, int],
) -> list[str]:
    lines: list[str] = []

    def walk(eid: str, ancestor_last: list[bool]) -> None:
        info = nodes[eid]
        prefix = "".join(("   " if last else glyphs["vert"] + "  ") for last in ancestor_last[:-1])
        if ancestor_last:
            prefix += glyphs["elbow"] if ancestor_last[-1] else glyphs["tee"]
        label, _ = _label(info, glyphs, use_color)
        retired = (
            f"  {_c(_DIM, glyphs['retired'] + ' retired by ' + info['retired_by'], use_color)}"
            if info["retired_by"]
            else ""
        )
        blocked = f"  {_blocked_text(info)}" if _blocked_text(info) else ""
        lines.append(f"{prefix}{label} {info['question']}{retired}{blocked}")
        kids = sorted(children.get(eid, []), key=lambda eid: at[eid])
        for i, kid in enumerate(kids):
            walk(kid, ancestor_last + [i == len(kids) - 1])

    for r in roots:
        walk(r, [])
    return lines


def _find_or_alloc(columns: list[str | None], label: str) -> int:
    """A column labelled `label`, reusing the leftmost freed one if none
    exists. The ledger's ids are monotonic and append-only, so processing
    newest-first means every column we need has either already been opened by
    a dependent, or never existed; there is no need for git's full graph
    algorithm to find it."""
    if label in columns:
        return columns.index(label)
    for i, c in enumerate(columns):
        if c is None:
            columns[i] = label
            return i
    columns.append(label)
    return len(columns) - 1


def _rail_lines(
    entries_desc: list[dict], nodes: dict[str, dict], glyphs: dict, use_color: bool, width: int
) -> list[str]:
    columns: list[str | None] = []
    rows: list[tuple[int, list[str | None], dict | None, Any]] = []

    for e in entries_desc:
        eid = e["id"]
        c = _find_or_alloc(columns, eid)
        # Every other column waiting on this id merges into c. The join has to
        # be drawn before the node row, or the lanes vanish and the picture
        # claims those dependents led nowhere.
        dupes = [i for i in range(len(columns)) if i != c and columns[i] == eid]
        if dupes:
            rows.append((c, list(columns), None, dupes))
            for i in dupes:
                columns[i] = None
        snapshot = list(columns)

        info = nodes[eid]
        supports = [s for s in info["supports"] if s in nodes]
        if not supports:
            columns[c] = None  # a root drops its column
        else:
            columns[c] = supports[0]
            for extra in supports[1:]:
                _find_or_alloc(columns, extra)
        # The node's column stays open only while it still awaits a support;
        # continuation rows read this to know whether to draw a lane under it.
        rows.append((c, snapshot, info, columns[c] is not None))

    lines: list[str] = []
    for c, snapshot, info, state in rows:
        if info is None:
            lines.append(_rail_join(snapshot, c, state, glyphs, use_color))
            continue

        plain_cells, cells = [], []
        for i in range(len(snapshot)):
            if i == c:
                plain_cells.append(glyphs["open"] if info["state"] == "open" else glyphs["bullet"])
                cells.append(_state_glyph(info["state"], glyphs, use_color))
            elif snapshot[i] is not None:
                plain_cells.append(glyphs["vert"])
                cells.append(_c(_DIM, glyphs["vert"], use_color))
            else:
                plain_cells.append(" ")
                cells.append(" ")
        lane, plain_lane = " ".join(cells), " ".join(plain_cells)

        # A continuation row shows lanes only. Reusing plain_lane here drew the
        # node's own glyph again on every wrapped line.
        cont_cells = list(plain_cells)
        cont_cells[c] = glyphs["vert"] if state else " "
        label = _id_state(info)
        avail = max(width - len(plain_lane) - 1 - len(label) - 1, 20)
        text = info["question"]
        extras = info["supports"][1:]
        if extras:
            text += "  (also <- %s)" % ", ".join(extras)
        if len(info["sets"]) > 1:
            text += "\n" + _formula(info["sets"])
        if info["retired_by"]:
            text += "\n" + f"{glyphs['retired']} retired by {info['retired_by']}"
        if _blocked_text(info):
            text += "\n" + _blocked_text(info)
        wrapped: list[str] = []
        for para in text.split("\n"):
            wrapped.extend(textwrap.wrap(para, width=avail) or [""])
        cont = " ".join(cont_cells) + " " * (len(label) + 2)
        lines.append(f"{lane} {label} {wrapped[0]}")
        for extra_line in wrapped[1:]:
            lines.append(f"{cont}{extra_line}")
    return lines


def _rail_join(
    columns: list[str | None], c: int, dupes: list[int], glyphs: dict, use_color: bool
) -> str:
    """The row that merges every lane awaiting one id back into column c.

    c is always the leftmost such column, because _find_or_alloc returns the
    first match, so the join only ever runs rightwards.
    """
    last = max(dupes)
    cells = []
    for i in range(len(columns)):
        if i == c:
            cells.append(glyphs["ltee"])
        elif i == last:
            cells.append(glyphs["corner"])
        elif i in dupes:
            cells.append(glyphs["join"])
        elif columns[i] is not None:
            # An unrelated lane the join has to cross.
            cells.append(glyphs["cross"] if c < i < last else glyphs["vert"])
        else:
            cells.append(glyphs["hbar"] if c < i < last else " ")
    row = ""
    for i, cell in enumerate(cells):
        row += cell
        if i < len(cells) - 1:
            row += glyphs["hbar"] if c <= i < last else " "
    return _c(_DIM, row, use_color)


def _render_graph(
    entries: list[dict], retired: dict[str, str], args: argparse.Namespace, style: str
) -> int:
    use_color = False if args.plain else True if args.pretty else _use_color()
    glyphs = _GRAPH_GLYPHS if _use_glyphs() else _GRAPH_GLYPHS_ASCII
    width = shutil.get_terminal_size().columns
    nodes = {e["id"]: _node_info(e, retired) for e in entries}
    at = positions(entries)
    entries_desc = sorted(entries, key=lambda e: at[e["id"]], reverse=True)

    if style == "rail":
        lines = _rail_lines(entries_desc, nodes, glyphs, use_color, width)
    else:
        roots = _forest_roots(entries, nodes, at)
        children = _forest_children(entries, nodes, roots, at)
        if style == "compact":
            lines = _compact_lines(nodes, roots, children, glyphs, use_color, at)
        else:
            lines = _forest_lines(nodes, roots, children, glyphs, use_color, width, at)

    print("\n".join(lines))
    return 0


def _write_csv(entries: list[dict], args: argparse.Namespace) -> int:
    """Write nodes.csv and edges.csv for Gephi into args.out."""

    from pathlib import Path

    from docket.graph_export import to_csv

    nodes, edges = to_csv(
        entries,
        detail=args.detail,
        superseded=bool(getattr(args, "superseded", False)),
    )
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


def cmd_graph(args: argparse.Namespace) -> int:
    style = getattr(args, "style", None)
    interactive = bool(getattr(args, "interactive", False))
    no_interactive = bool(getattr(args, "no_interactive", False))
    plain = bool(getattr(args, "plain", False))
    # getattr, not args.format: the dispatch tests build a bare namespace.
    fmt = getattr(args, "format", None)

    if interactive and no_interactive:
        print("docket: --interactive conflicts with --no-interactive", file=sys.stderr)
        return 2
    if interactive and plain:
        print("docket: --interactive conflicts with --plain", file=sys.stderr)
        return 2
    if interactive and style is not None:
        print("docket: --interactive conflicts with --style", file=sys.stderr)
        return 2
    if interactive and fmt:
        print("docket: --interactive conflicts with --format", file=sys.stderr)
        return 2
    if getattr(args, "out", None) and fmt != "csv":
        print("docket: --out belongs to --format csv", file=sys.stderr)
        return 2
    if fmt == "csv" and not getattr(args, "out", None):
        # Gephi imports a node table and an edge table separately, so csv is
        # two documents and stdout cannot carry both.
        print("docket: --format csv writes two files; name a directory with --out", file=sys.stderr)
        return 2
    if interactive and not _graph_is_tty():
        print("docket: --interactive requires terminal stdin and stdout", file=sys.stderr)
        return 1

    entries, retired = _graph_entries(args)
    if not entries:
        print("docket: nothing recorded")
        return 0

    if fmt == "csv":
        return _write_csv(entries, args)

    if fmt:
        from docket.graph_export import to_dot, to_mermaid

        render = to_dot if args.format == "dot" else to_mermaid
        text = render(
            entries,
            detail=args.detail,
            direction=args.direction,
            superseded=bool(getattr(args, "superseded", False)),
        )
        if not text:
            print("docket: no record in this selection carries a relation", file=sys.stderr)
            return 0
        print(text)
        return 0

    viewer = _graph_viewer_path()
    auto = _graph_is_tty() and not no_interactive and not plain and style is None

    if interactive or auto:
        if not viewer.is_file():
            _graph_viewer_error(viewer)
            if interactive:
                return 1
            return _render_graph(entries, retired, args, "compact")
        return _run_graph_viewer(entries, retired, pretty=bool(getattr(args, "pretty", False)))

    return _render_graph(entries, retired, args, style or "forest")
