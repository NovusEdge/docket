"""Render the ledger's relation graph as a mermaid flowchart.

Mermaid because it needs no install anywhere the project already lives:
GitHub and GitLab render it in a fence, and so does the GitBook site this
project publishes. Graphviz would lay out a hundred nodes better and produce a
real SVG, at the cost of making the reader install graphviz to see anything.
"""

from __future__ import annotations

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


def to_mermaid(
    entries: list[dict[str, Any]],
    *,
    detail: int = 40,
    direction: str = "LR",
    superseded: bool = False,
) -> str:
    """A mermaid flowchart of the relations between these records.

    Records with no relation are left out. A node alone on the canvas carries
    nothing a list does not already say.
    """

    kept = [e for e in entries if superseded or not e.get("retired_by")]
    known = {str(e["id"]) for e in kept}
    edges = [(a, b, k) for a, b, k in _edges(kept) if a in known or "_set" in a]
    edges = [(a, b, k) for a, b, k in edges if b in known or "_set" in b]

    linked = {end for edge in edges for end in edge[:2]}
    drawn = [e for e in kept if str(e["id"]) in linked]
    if not drawn:
        return ""

    lines = [f"flowchart {direction}"]
    for entry in drawn:
        open_mark, close_mark = SHAPES.get(str(entry.get("kind")), ("[", "]"))
        lines.append(f'  {entry["id"]}{open_mark}"{_label(entry, detail)}"{close_mark}')
    for join in sorted(
        {a for a, _, _ in edges if "_set" in a} | {b for _, b, _ in edges if "_set" in b}
    ):
        lines.append(f'  {join}(("set"))')
    for source, target, kind in edges:
        lines.append(f"  {source} {ARROWS[kind]} {target}")

    lines.append("  classDef default fill:#ffffff,stroke:#0a0a0a,color:#0a0a0a")
    retired = [str(e["id"]) for e in drawn if e.get("retired_by")]
    if retired:
        lines.append("  classDef retired fill:#f3f3f3,stroke:#8a8a8a,color:#6a6a6a")
        lines.append(f"  class {','.join(retired)} retired")
    return "\n".join(lines)


__all__ = ["ARROWS", "SHAPES", "to_mermaid"]
