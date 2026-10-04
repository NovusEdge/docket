"""Render the ledger's relation graph as mermaid or graphviz DOT.

Mermaid renders with nothing installed where this project already lives:
GitHub and GitLab render it in a fence, and so does the GitBook site. DOT
needs graphviz, which the reader installs, and pays for it with a layout that
holds up past a hundred nodes and with real SVG, PDF and PNG output.

Both formats read the same edge model below, so a schema change touches one
place.
"""

from __future__ import annotations

import textwrap
from collections.abc import Mapping
from typing import Any

from docket import support
from docket.graph_layout import (
    arrange,
    box_tree,
    dot_clusters,
    focus_edges,
    grid_edges,
    mermaid_clusters,
)

# One arrow per relation, so the four read apart without a legend. supersedes
# carries a label because a plain arrow between two decisions says nothing
# about which one won.
ARROWS = {
    "supports": "-->",
    "depends_on": "-.->",
    "answers": "==>",
    "supersedes": "-- retires -->",
}

SHAPES = {
    "decision": ("[", "]"),
    "claim": ("([", "])"),
    "question": ("{{", "}}"),
}

_ESCAPES = str.maketrans({'"': "'", "\n": " ", "\r": " "})


def _label(entry: Mapping[str, Any], detail: int) -> str:
    text = str(entry.get("text", "")).translate(_ESCAPES).strip()
    if detail <= 0 or not text:
        return str(entry["id"])
    if len(text) > detail:
        text = text[: detail - 1].rstrip() + "…"
    return f"{entry['id']} {text}"


def _edges(entries: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """Every relation, as (from, to, kind), in a stable order.

    supports points from the supporting record to the record it holds up, so
    an arrow reads in the direction the reasoning flows. The other three point
    from the record that declared the link.
    """

    result: list[tuple[str, str, str]] = []
    for entry in entries:
        ident = str(entry["id"])
        groups = entry.get("supports") or []
        # A join node only where a record carries more than one support set.
        # supports is a list of lists and each inner list is one complete
        # justification, so flattening several of them into one fan-in would
        # draw a record as needing every premise when it needs one set.
        if len(groups) > 1:
            for index, group in enumerate(groups, 1):
                join = f"{ident}_set{index}"
                for target in group:
                    result.append((str(target), join, "supports"))
                result.append((join, ident, "supports"))
        else:
            for group in groups:
                for target in group:
                    result.append((str(target), ident, "supports"))
        for field in ("depends_on", "answers", "supersedes"):
            for target in entry.get(field) or []:
                result.append((ident, str(target), field))
    return result


def _support_mark(entry: Mapping[str, Any]) -> str:
    """ "flagged" or "unsupported" when a reader of the record would see it."""

    for status in ("unsupported", "flagged"):
        if support.surfaced(entry, status):
            return status
    return ""


def _join_nodes(edges: list[tuple[str, str, str]]) -> list[str]:
    ends = {a for a, _, _ in edges} | {b for _, b, _ in edges}
    return sorted(end for end in ends if "_set" in end)


def _selected(
    entries: list[dict[str, Any]],
    *,
    superseded: bool,
    focus: str | None = None,
    hops: int = 2,
    orphans: bool = False,
) -> tuple[list[dict[str, Any]], list[tuple[str, str, str]]]:
    """The records to draw and the edges between them.

    Every format reads this, so a schema change touches one place. A record
    with no relation in the selection is left out unless `orphans` is set,
    except the focused one: it is in the selection, so it draws alone rather
    than being reported as missing. Relations to hidden retired records still
    count, or a record that retired another would vanish along with it.
    """

    def inside(ids: set[str], source: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
        return [
            (a, b, k)
            for a, b, k in _edges(source)
            if (a in ids or "_set" in a) and (b in ids or "_set" in b)
        ]

    kept = [e for e in entries if superseded or not e.get("retired_by")]
    known = {str(e["id"]) for e in kept}
    edges = inside(known, kept)
    linked = {end for edge in inside({str(e["id"]) for e in entries}, entries) for end in edge[:2]}
    drawn = kept if orphans else [e for e in kept if str(e["id"]) in linked]
    if focus is not None:
        # Focus walks the edges that survive retirement, so a retired record is
        # never a stepping stone unless it is drawn.
        keep, edges = focus_edges(edges, known, focus, hops)
        drawn = [e for e in kept if str(e["id"]) in keep]
    return drawn, edges


def to_mermaid(
    entries: list[dict[str, Any]],
    *,
    detail: int = 40,
    direction: str = "LR",
    superseded: bool = False,
    group: str = "none",
    focus: str | None = None,
    hops: int = 2,
    orphans: bool = False,
) -> str:
    """A mermaid flowchart of the relations between these records."""

    drawn, edges = _selected(
        entries, superseded=superseded, focus=focus, hops=hops, orphans=orphans
    )
    if not drawn:
        return ""

    lines = [f"flowchart {direction}"]
    nodes = {}
    for entry in drawn:
        open_mark, close_mark = SHAPES.get(str(entry.get("kind")), ("[", "]"))
        nodes[str(entry["id"])] = f'{entry["id"]}{open_mark}"{_label(entry, detail)}"{close_mark}'
    lines += arrange(drawn, group, nodes, mermaid_clusters)
    for join in _join_nodes(edges):
        lines.append(f'  {join}(("set"))')
    for source, target, kind in edges:
        lines.append(f"  {source} {ARROWS[kind]} {target}")

    lines.append("  classDef default fill:#ffffff,stroke:#0a0a0a,color:#0a0a0a")
    retired = [str(e["id"]) for e in drawn if e.get("retired_by")]
    if retired:
        lines.append("  classDef retired fill:#f3f3f3,stroke:#8a8a8a,color:#6a6a6a")
        lines.append(f"  class {','.join(retired)} retired")
    for status, dashes in MERMAID_DASHES.items():
        marked = [str(e["id"]) for e in drawn if _support_mark(e) == status]
        if marked:
            lines.append(f"  classDef {status} stroke-dasharray:{dashes}")
            lines.append(f"  class {','.join(marked)} {status}")
    return "\n".join(lines)


# The border carries support status in both formats, so it survives a black and
# white print and leaves the fill free for the retired grey.
MERMAID_DASHES = {"flagged": "6 3", "unsupported": "2 2"}
DOT_BORDERS = {"flagged": "dashed", "unsupported": "dotted"}


DOT_SHAPES = {
    "decision": "box",
    "claim": "ellipse",
    "question": "hexagon",
}

# Graphviz has no arrow vocabulary as compact as mermaid's, so the relations
# separate on style and arrowhead together. Colour is not used: a graph printed
# in black and white has to stay readable.
DOT_EDGES = {
    "supports": "style=solid, arrowhead=normal",
    "depends_on": "style=dashed, arrowhead=empty",
    "answers": "style=bold, arrowhead=vee",
    "supersedes": 'style=solid, arrowhead=box, label="retires", fontsize=9',
}


DOT_EDGE_CLASSES = {
    "supports": "supports",
    "depends_on": "depends_on",
    "answers": "answers",
    "supersedes": "retires",
}


def _dot_classes(entry: Mapping[str, Any], focused: bool = False) -> str:
    words = [str(entry.get("kind", "")), str(entry.get("state", ""))]
    if entry.get("retired_by"):
        words.append("retired")
    elif mark := _support_mark(entry):
        words.append(mark)
    if focused:
        words.append("focus")
    return " ".join(w for w in words if w)


def _dot_quote(text: str) -> str:
    """Escape for a DOT quoted string, where a backslash also escapes itself."""

    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


# A hexagon or an ellipse grows sideways to hold its label, so one long line
# turns a question node into a lozenge wider than the rest of the graph.
# Wrapping keeps every shape near its natural proportions.
DOT_WRAP = 26


def _dot_label(entry: Mapping[str, Any], detail: int) -> str:
    text = str(entry.get("text", "")).strip()
    ident = _dot_quote(str(entry["id"]))
    if detail <= 0 or not text:
        return ident
    if len(text) > detail:
        text = text[: detail - 1].rstrip() + "..."
    # \n inside a DOT label is a line break, so the id sits above its text.
    wrapped = textwrap.wrap(text, DOT_WRAP) or [text]
    return "\\n".join([ident, *(_dot_quote(line) for line in wrapped)])


def to_dot(
    entries: list[dict[str, Any]],
    *,
    detail: int = 40,
    direction: str = "LR",
    superseded: bool = False,
    group: str = "none",
    focus: str | None = None,
    hops: int = 2,
    orphans: bool = False,
) -> str:
    """A graphviz digraph of the relations between these records.

    `group` boxes records by "kind" or "scope"; `focus` keeps the record and
    those within `hops` relation steps, and raises ValueError if it is not drawn.
    """

    drawn, edges = _selected(
        entries, superseded=superseded, focus=focus, hops=hops, orphans=orphans
    )
    if not drawn:
        return ""

    lines = [
        "digraph docket {",
        f"  rankdir={direction};",
        # Without packing, a ledger of many small components lays out left to
        # right as one tall column. "array" without the u flag places the
        # largest components first, so related records lead and lone ones trail.
        '  pack=true; packmode="array";',
        '  bgcolor="white";',
        '  node [fontname="Helvetica", fontsize=10, color="#0a0a0a", fontcolor="#0a0a0a"];',
        '  edge [fontname="Helvetica", color="#0a0a0a", fontcolor="#0a0a0a"];',
    ]
    nodes = {}
    for entry in drawn:
        shape = DOT_SHAPES.get(str(entry.get("kind")), "box")
        attrs = f'shape={shape}, label="{_dot_label(entry, detail)}"'
        if entry.get("retired_by"):
            attrs += ', style=filled, fillcolor="#f3f3f3", color="#8a8a8a", fontcolor="#6a6a6a"'
        elif mark := _support_mark(entry):
            attrs += f", style={DOT_BORDERS[mark]}"
        is_focus = str(entry["id"]) == focus
        attrs += f', class="{_dot_classes(entry, is_focus)}"' + (
            ", penwidth=2.5" if is_focus else ""
        )
        nodes[str(entry["id"])] = f'"{entry["id"]}" [{attrs}];'
    lines += arrange(drawn, group, nodes, dot_clusters)
    for join in _join_nodes(edges):
        lines.append(
            f'  "{join}" [shape=point, width=0.08, xlabel="set", fontsize=8, class="join"];'
        )
    for source, target, kind in edges:
        lines.append(
            f'  "{source}" -> "{target}" [{DOT_EDGES[kind]}, class="{DOT_EDGE_CLASSES[kind]}"];'
        )
    if group != "none":
        linked = {end for edge in edges for end in edge[:2]}
        for a, b in grid_edges(box_tree(drawn, group)[0], linked):
            lines.append(f'  "{a}" -> "{b}" [style=invis];')
    lines.append("}")
    return "\n".join(lines)


NODE_COLUMNS = ("Id", "Label", "kind", "state", "retired", "scope", "text", "support")
EDGE_COLUMNS = ("Source", "Target", "Type", "Label", "Weight")


def to_csv(
    entries: list[dict[str, Any]],
    *,
    detail: int = 40,
    superseded: bool = False,
    focus: str | None = None,
    hops: int = 2,
    orphans: bool = False,
) -> tuple[str, str]:
    """A Gephi node table and edge table, as two CSV documents.

    Gephi imports one spreadsheet at a time as either nodes or edges, so this
    returns two rather than one. The capitalised column names are the ones its
    importer recognises without a manual mapping; the lowercase ones arrive as
    node attributes a filter or a partition can use.

    A join node carries kind "set" so a partition by kind separates the
    synthetic nodes from the records.
    """

    import csv
    import io

    drawn, edges = _selected(
        entries, superseded=superseded, focus=focus, hops=hops, orphans=orphans
    )
    if not drawn:
        return "", ""

    nodes = io.StringIO()
    writer = csv.writer(nodes, lineterminator="\n")
    writer.writerow(NODE_COLUMNS)
    for entry in drawn:
        writer.writerow(
            [
                entry["id"],
                _label(entry, detail),
                entry.get("kind", ""),
                entry.get("state", ""),
                "true" if entry.get("retired_by") else "false",
                " ".join(str(s) for s in entry.get("scope") or []),
                str(entry.get("text", "")),
                _support_mark(entry),
            ]
        )
    for join in _join_nodes(edges):
        writer.writerow([join, "set", "set", "", "false", "", "", ""])

    links = io.StringIO()
    writer = csv.writer(links, lineterminator="\n")
    writer.writerow(EDGE_COLUMNS)
    for source, target, kind in edges:
        writer.writerow([source, target, "Directed", kind, 1])
    return nodes.getvalue(), links.getvalue()


__all__ = [
    "ARROWS",
    "DOT_EDGES",
    "DOT_EDGE_CLASSES",
    "DOT_SHAPES",
    "EDGE_COLUMNS",
    "NODE_COLUMNS",
    "SHAPES",
    "to_csv",
    "to_dot",
    "to_mermaid",
]
