"""Layout controls for the relation graph: focus on a neighbourhood, group into boxes.

graph_export imports this module, so nothing here may import graph_export at
load time; callers pass the edges in.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
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
                queue.appendleft(nxt) if cost == 0 else queue.append(nxt)
    return {n for n in best if "_set" not in n}


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
