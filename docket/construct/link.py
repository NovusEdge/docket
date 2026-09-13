"""Pass 2: the relations between proposals, and what the local rules allow.

A per-document extraction cannot see another document, so it can only ever emit
a flat list. Relations need one call over the whole set. The model proposes
edges; everything here decides which of them survive.
"""

from __future__ import annotations

EDGE_KINDS = ("supports", "supersedes")

# Sent to the linker in place of the documents. The spike's 61 records are
# about 2.8k tokens like this, against the 15k words they came from.
_PAYLOAD_FIELDS = ("kind", "text", "choice")


def _label(index: int) -> str:
    return f"p{index + 1}"


def payload(proposals: list[dict]) -> list[dict]:
    """The proposal set as the linker sees it: labelled, and stripped to the
    fields a relation can be argued from."""
    rows = []
    for index, item in enumerate(proposals):
        row = {"id": _label(index)}
        row.update({field: item.get(field, "") for field in _PAYLOAD_FIELDS})
        row["path"] = item["source"]["path"]
        row["date"] = item["source"]["date"]
        rows.append(row)
    return rows


def labels(proposals: list[dict]) -> dict[str, str]:
    """Each label mapped to the identity key it stands for."""
    return {_label(index): item["key"] for index, item in enumerate(proposals)}


def _reaches(edges: list[tuple[str, str]], start: str, target: str) -> bool:
    """Whether target is reachable from start along the given edges."""
    seen = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(head for tail, head in edges if tail == node)
    return False


def validate(edges: list[dict], proposals: list[dict]) -> tuple[list[dict], list[str]]:
    """The edges that hold, and one message per edge dropped.

    A failing edge is dropped with a warning rather than failing the run: a
    linker that gets one relation wrong out of five hundred should not cost the
    other four hundred and ninety-nine.
    """
    known = {_label(index): item for index, item in enumerate(proposals)}
    kept: list[dict] = []
    dropped: list[str] = []
    supports: list[tuple[str, str]] = []

    for edge in edges:
        kind, tail, head = edge.get("kind"), edge.get("from"), edge.get("to")
        where = f"{kind} {tail} -> {head}"

        if kind not in EDGE_KINDS:
            dropped.append(f"{where}: unknown edge kind {kind!r}")
            continue
        for name in (tail, head):
            if name not in known:
                dropped.append(f"{where}: no record {name!r}")
                break
        else:
            if tail == head:
                dropped.append(f"{where}: a record cannot relate to itself")
                continue

            source, target = known[tail], known[head]

            if kind == "supersedes":
                if source["kind"] != target["kind"]:
                    dropped.append(f"{where}: supersession needs one kind, "
                                   f"got {source['kind']} and {target['kind']}")
                    continue
                later, earlier = source["source"]["date"], target["source"]["date"]
                if not later or not earlier:
                    dropped.append(f"{where}: supersession needs a date on both records")
                    continue
                if later <= earlier:
                    dropped.append(f"{where}: {tail} is earlier than or same-day as "
                                   f"{head}, so it cannot supersede it")
                    continue

            if kind == "supports":
                # The new edge points tail -> head, so a path from head back to
                # tail would close a loop.
                if _reaches(supports, head, tail):
                    dropped.append(f"{where}: closes a support cycle")
                    continue
                supports.append((tail, head))

            kept.append(edge)

    return kept, dropped


def apply(edges: list[dict], proposals: list[dict]) -> list[dict]:
    """The proposals carrying their validated relations, keyed by identity.

    Support lands as a single justification set. Alternative sets are a thing a
    human adds later; a linker has no way to tell two independent grounds from
    two halves of one.
    """
    key_of = labels(proposals)
    out = [dict(item) for item in proposals]
    index_of = {_label(index): index for index in range(len(proposals))}

    grouped: dict[str, list[str]] = {}
    for edge in edges:
        target_key = key_of[edge["to"]]
        if edge["kind"] == "supports":
            grouped.setdefault(edge["from"], []).append(target_key)
        else:
            record = out[index_of[edge["from"]]]
            record.setdefault("supersedes", []).append(target_key)

    for tail, keys in grouped.items():
        out[index_of[tail]]["supports"] = [keys]

    for record in out:
        record.setdefault("supports", [])
        record.setdefault("supersedes", [])
    return out
