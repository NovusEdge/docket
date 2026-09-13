"""Pass 2: the relations between proposals, and what the local rules allow.

A per-document extraction cannot see another document, so it can only ever emit
a flat list. Relations need one call over the whole set. The model proposes
edges; everything here decides which of them survive.
"""

from __future__ import annotations

from docket.construct import schema

# `contradicts` never lands on a record. Two records that disagree become a
# question naming both, because deciding which one survives is the author's
# call and a linker has no standing to make it.
EDGE_KINDS = ("supports", "supersedes", "contradicts")

# One call over 843 records produced 23 edges. Records from one document relate
# most reliably, so a batch keeps documents whole and lets neighbours co-occur.
BATCH = 120

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
    retired: dict[str, str] = {}

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

            if kind == "contradicts":
                # Nothing to check beyond the endpoints: a disagreement needs no
                # shared kind, no dates, and no ordering.
                kept.append(edge)
                continue

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
                if head in retired:
                    # The ledger retires a target once and refuses the second
                    # append. Acceptance has no transaction, so an edge that
                    # aborts there leaves records written and the stage untouched.
                    dropped.append(f"{where}: {head} is already superseded by "
                                   f"{retired[head]}")
                    continue
                retired[head] = tail

            if kind == "supports":
                if target["kind"] == "question":
                    # ledger.py refuses support pointing at a question: an
                    # inquiry is not a ground.
                    dropped.append(f"{where}: {head} is a question, which cannot "
                                   "ground anything")
                    continue
                # The new edge points tail -> head, so a path from head back to
                # tail would close a loop.
                if _reaches(supports, head, tail):
                    dropped.append(f"{where}: closes a support cycle")
                    continue
                supports.append((tail, head))

            kept.append(edge)

    return kept, dropped


def questions(edges: list[dict], proposals: list[dict]) -> list[dict]:
    """One proposed question per contradiction, naming both records.

    Two faithful records can disagree because their documents were written
    months apart. Recording a silent supersedes would pick a winner the sources
    do not; a question puts the choice in front of whoever owns it.

    The question anchors on the first record's source line, so a reviewer still
    has a document to open and the key stays stable across runs.
    """
    known = {_label(index): item for index, item in enumerate(proposals)}
    asked = []
    for edge in edges:
        if edge.get("kind") != "contradicts":
            continue
        first, second = known.get(edge["from"]), known.get(edge["to"])
        if not first or not second:
            continue
        asked.append(schema.proposal(
            kind="question",
            text=(f"Which holds? {first['text']} "
                  f"Against: {second['text']}"),
            anchor=first["anchor"],
            key_kind="contradiction",
            rationale=(f"Extraction found both, from {first['source']['path']} "
                       f"and {second['source']['path']}. Neither source settles it."),
            source=dict(first["source"]),
            confidence="low",
        ))
    return asked


def batches(proposals: list[dict], size: int = BATCH) -> list[list[dict]]:
    """The proposal set split into linkable chunks, documents kept whole.

    A single call over the whole set does not scale: 843 records yielded 23
    edges. Splitting loses edges that cross a boundary, and keeping each
    document intact preserves the ones most likely to be real.
    """
    if size <= 0 or len(proposals) <= size:
        return [list(proposals)]

    grouped: dict[str, list[dict]] = {}
    for item in proposals:
        grouped.setdefault(item["source"]["path"], []).append(item)

    out: list[list[dict]] = []
    current: list[dict] = []
    for path in sorted(grouped):
        group = grouped[path]
        if current and len(current) + len(group) > size:
            out.append(current)
            current = []
        current.extend(group)
    if current:
        out.append(current)
    return out


def apply(edges: list[dict], proposals: list[dict]) -> list[dict]:
    """The proposals carrying their validated relations, keyed by identity.

    Support lands as a single justification set. Alternative sets are a thing a
    human adds later; a linker has no way to tell two independent grounds from
    two halves of one.
    """
    key_of = labels(proposals)
    # Deep enough to own every list this function appends to, so an input
    # record's own relations are never mutated.
    out = [{**item,
            "supports": [list(group) for group in item.get("supports") or []],
            "supersedes": list(item.get("supersedes") or [])}
           for item in proposals]
    index_of = {_label(index): index for index in range(len(proposals))}

    for edge in edges:
        if edge["kind"] == "contradicts":
            # Lands on neither record; questions() turns it into its own.
            continue
        record = out[index_of[edge["from"]]]
        target_key = key_of[edge["to"]]
        if edge["kind"] == "supports":
            # One set per ground. docket/ledger.py reads supports as a list of
            # conjunctive sets, so joining two grounds into one set would claim
            # both are required, which is more than the linker saw.
            record["supports"].append([target_key])
        else:
            record["supersedes"].append(target_key)
    return out
