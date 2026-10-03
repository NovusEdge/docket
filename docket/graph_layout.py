"""Layout controls for the relation graph: focus on a neighbourhood, group into boxes.

graph_export imports this module, so nothing here may import graph_export at
load time; callers pass the edges in.
"""

from __future__ import annotations

import itertools
import re
from collections import defaultdict, deque
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

_GLOB = re.compile(r"[*?\[]")


def neighbourhood(
    edges: list[tuple[str, str, str]], ids: set[str], focus: str, hops: int
) -> set[str]:
    """Record ids within `hops` relation steps of `focus`, in either direction.

    A join node (`<id>_setN`) is part of an edge, so crossing one costs no hop.
    """

    if focus not in ids:
        raise ValueError(f"{focus} is not in this selection")
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b, _ in edges:
        adj[a].add(b)
        adj[b].add(a)
    # 0-1 BFS; a node first reached far away can be relaxed later through a join.
    best = {focus: 0}
    queue = deque([focus])
    while queue:
        node = queue.popleft()
        for nxt in adj[node]:
            cost = 0 if "_set" in nxt else 1
            dist = best[node] + cost
            if dist <= hops and dist < best.get(nxt, hops + 1):
                best[nxt] = dist
                if cost == 0:
                    queue.appendleft(nxt)
                else:
                    queue.append(nxt)
    return {n for n in best if "_set" not in n}


def focus_edges(
    edges: list[tuple[str, str, str]], ids: set[str], focus: str, hops: int
) -> tuple[set[str], list[tuple[str, str, str]]]:
    """The neighbourhood's record ids and the edges that stay drawn.

    A join node survives only with an input and its output both inside, so a
    cut set never dangles.
    """

    keep = neighbourhood(edges, ids, focus, hops)
    inside = [e for e in edges if all(n in keep or "_set" in n for n in e[:2])]
    live = {b for _, b, _ in inside if "_set" in b} & {a for a, _, _ in inside if "_set" in a}
    return keep, [e for e in inside if all("_set" not in n or n in live for n in e[:2])]


def scope_dir(scope: str) -> tuple[str, ...]:
    """Components before the first glob component, or before the last one if none."""

    parts = scope.split("/")
    out: list[str] = []
    for i, part in enumerate(parts):
        if _GLOB.search(part) or i == len(parts) - 1:
            break
        out.append(part)
    return tuple(out)


def box_path(scopes: list[str]) -> tuple[str, ...] | None:
    """The deepest directory every scope shares; None without scopes, () for `/`."""

    dirs = [scope_dir(p.strip()) for s in scopes for p in s.split(",") if p.strip()]
    if not dirs:
        return None
    common = dirs[0]
    for d in dirs[1:]:
        n = 0
        while n < min(len(common), len(d)) and common[n] == d[n]:
            n += 1
        common = common[:n]
    return common


@dataclass
class Box:
    label: str
    ids: list[str] = field(default_factory=list)
    children: dict[str, Box] = field(default_factory=dict)


def _merge(box: Box) -> Box:
    """Fold boxes that hold no records and a single child into that child."""

    box.children = {k: _merge(c) for k, c in box.children.items()}
    while not box.ids and len(box.children) == 1:
        (child,) = box.children.values()
        box = Box(box.label + child.label, child.ids, child.children)
    return box


def box_tree(entries: list[dict[str, Any]], group: str) -> tuple[Box, list[str]]:
    """The box tree for `group` ("kind" or "scope") and the ids left outside it.

    The root is never merged away and its label is unused.
    """

    root = Box("")
    loose: list[str] = []
    for e in entries:
        ident = str(e["id"])
        if group == "kind":
            name = f"{e['kind']}s"
            root.children.setdefault(name, Box(name)).ids.append(ident)
            continue
        path = box_path(e.get("scope") or [])
        if path is None:
            loose.append(ident)
            continue
        box = root
        for part in path or ("",):
            name = f"{part}/"
            box = box.children.setdefault(name, Box(name))
        box.ids.append(ident)
    root.children = {k: _merge(c) for k, c in root.children.items()}
    return root, loose


GROUPS = ("none", "kind", "scope")


def _clusters(
    box: Box,
    lines: Mapping[str, str],
    depth: int,
    counter: Iterator[int],
    head: Callable[[int, str], list[str]],
    foot: str,
) -> list[str]:
    pad = "  " * depth
    out: list[str] = []
    for child in box.children.values():
        out += [pad + h for h in head(next(counter), child.label)]
        out += [f"{pad}  {lines[i]}" for i in child.ids]
        out += _clusters(child, lines, depth + 1, counter, head, foot)
        out.append(pad + foot)
    return out


def _dot_head(n: int, label: str) -> list[str]:
    text = label.replace("\\", "\\\\").replace('"', '\\"')
    return [
        f"subgraph cluster_{n} {{",
        f'  label="{text}"; class="group"; labeljust=l; fontname="monospace"; fontsize=18; margin=14;',
    ]


def dot_clusters(box: Box, lines: Mapping[str, str], depth: int = 1) -> list[str]:
    """Nested `subgraph cluster_N` blocks for the root's children; `lines` maps id to node line."""

    return _clusters(box, lines, depth, itertools.count(), _dot_head, "}")


def mermaid_clusters(box: Box, lines: Mapping[str, str], depth: int = 1) -> list[str]:
    """Nested `subgraph g_N ["label"]` blocks; the `g_` prefix cannot collide with a record id."""

    def head(n: int, label: str) -> list[str]:
        return [f'subgraph g_{n} ["{label.replace(chr(34), chr(39))}"]']

    return _clusters(box, lines, depth, itertools.count(), head, "end")


def arrange(
    drawn: list[dict[str, Any]],
    group: str,
    lines: Mapping[str, str],
    clusters: Callable[[Box, Mapping[str, str]], list[str]],
) -> list[str]:
    """Node lines in `lines` order, or boxed by `group`, with records outside any box last."""

    if group not in GROUPS:
        raise ValueError(f"group must be one of {', '.join(GROUPS)}, not {group}")
    if group == "none":
        return [f"  {line}" for line in lines.values()]
    root, loose = box_tree(drawn, group)
    return clusters(root, lines) + [f"  {lines[i]}" for i in loose]
