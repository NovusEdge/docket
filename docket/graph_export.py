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


def _join_nodes(edges: list[tuple[str, str, str]]) -> list[str]:
    ends = {a for a, _, _ in edges} | {b for _, b, _ in edges}
    return sorted(end for end in ends if "_set" in end)


def _selected(
    entries: list[dict[str, Any]], *, superseded: bool
) -> tuple[list[dict[str, Any]], list[tuple[str, str, str]]]:
    """The records to draw and the edges between them.

    Both formats read this, so a schema change touches one place. A record
    with no relation is left out: a node alone on the canvas carries nothing a
    list line does not already say.
    """

    kept = [e for e in entries if superseded or not e.get("retired_by")]
    known = {str(e["id"]) for e in kept}
    edges = [
        (a, b, k)
        for a, b, k in _edges(kept)
        if (a in known or "_set" in a) and (b in known or "_set" in b)
    ]
    linked = {end for edge in edges for end in edge[:2]}
    return [e for e in kept if str(e["id"]) in linked], edges


def to_mermaid(
    entries: list[dict[str, Any]],
    *,
    detail: int = 40,
    direction: str = "LR",
    superseded: bool = False,
) -> str:
    """A mermaid flowchart of the relations between these records."""

    drawn, edges = _selected(entries, superseded=superseded)
    if not drawn:
        return ""

    lines = [f"flowchart {direction}"]
    for entry in drawn:
        open_mark, close_mark = SHAPES.get(str(entry.get("kind")), ("[", "]"))
        lines.append(f'  {entry["id"]}{open_mark}"{_label(entry, detail)}"{close_mark}')
    for join in _join_nodes(edges):
        lines.append(f'  {join}(("set"))')
    for source, target, kind in edges:
        lines.append(f"  {source} {ARROWS[kind]} {target}")

    lines.append("  classDef default fill:#ffffff,stroke:#0a0a0a,color:#0a0a0a")
    retired = [str(e["id"]) for e in drawn if e.get("retired_by")]
    if retired:
        lines.append("  classDef retired fill:#f3f3f3,stroke:#8a8a8a,color:#6a6a6a")
        lines.append(f"  class {','.join(retired)} retired")
    return "\n".join(lines)


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
) -> str:
    """A graphviz digraph of the relations between these records."""

    drawn, edges = _selected(entries, superseded=superseded)
    if not drawn:
        return ""

    lines = [
        "digraph docket {",
        f"  rankdir={direction};",
        '  bgcolor="white";',
        '  node [fontname="Helvetica", fontsize=10, color="#0a0a0a", fontcolor="#0a0a0a"];',
        '  edge [fontname="Helvetica", color="#0a0a0a", fontcolor="#0a0a0a"];',
    ]
    for entry in drawn:
        shape = DOT_SHAPES.get(str(entry.get("kind")), "box")
        attrs = f'shape={shape}, label="{_dot_label(entry, detail)}"'
        if entry.get("retired_by"):
            attrs += ', style=filled, fillcolor="#f3f3f3", color="#8a8a8a", fontcolor="#6a6a6a"'
        lines.append(f'  "{entry["id"]}" [{attrs}];')
    for join in _join_nodes(edges):
        lines.append(f'  "{join}" [shape=point, width=0.08, xlabel="set", fontsize=8];')
    for source, target, kind in edges:
        lines.append(f'  "{source}" -> "{target}" [{DOT_EDGES[kind]}];')
    lines.append("}")
    return "\n".join(lines)


__all__ = ["ARROWS", "DOT_EDGES", "DOT_SHAPES", "SHAPES", "to_dot", "to_mermaid"]
