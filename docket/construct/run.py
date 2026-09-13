"""The two-pass driver: documents in, staged proposals out.

Pass 1 reads one document per call and can only ever emit a flat list. Pass 2
sees the whole proposal set and proposes the relations between them. Everything
the model returns is checked locally before it is staged.

The provider call is injected, so the whole driver runs under test without a
key and without a network.
"""

from __future__ import annotations

import concurrent.futures
import json
import textwrap
from pathlib import Path

from docket.construct import client, extract, link, schema

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(schema.KINDS)},
                    "text": {"type": "string"},
                    "choice": {"type": "string"},
                    "rationale": {"type": "string"},
                    "anchor": {"type": "string"},
                    "scope": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["kind", "text", "anchor"],
            },
        },
    },
    "required": ["records"],
}

LINK_SCHEMA = {
    "type": "object",
    "properties": {
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(link.EDGE_KINDS)},
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                },
                "required": ["kind", "from", "to"],
            },
        },
    },
    "required": ["edges"],
}

_EXTRACT_PROMPT = """\
Read the document below and record the claims, decisions and open questions it
states. Record only what the document says; infer nothing it does not.

A claim is a premise the document asserts. A decision is a commitment it makes,
and needs the choice. A question is something it leaves open.

For every record, `anchor` must be one line copied verbatim from the document,
the line that carries the record. Do not paraphrase the anchor.

`scope` names the files or globs the record governs, as paths. Never prose.
Leave it empty when the document names none.

Where the document lists options it rejected, put them in `rationale`. Do not
record a rejected option as its own decision.

Document: {path}

{body}
"""

_LINK_PROMPT = """\
Below are records extracted from one project's documents, each with the document
it came from and that document's date.

Propose the relations between them.

`supports` means the second record is a ground for the first. `supersedes` means
the first record replaces the second: both must be the same kind, and the first
must come from a later date.

Propose nothing you cannot argue from the records shown. An empty list is a
valid answer.

{rows}
"""


class RunError(RuntimeError):
    """The run cannot proceed at all."""


def documents(paths: list[str]) -> list[Path]:
    """Every markdown file the given paths name, in a stable order."""
    found: list[Path] = []
    for name in paths:
        path = Path(name)
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            found.extend(sorted(path.rglob("*.md")))
    return sorted(dict.fromkeys(found))


def _default_caller():
    """The real provider call. Imported here, never at module scope."""
    from openai import OpenAI

    cfg = client.config()
    api = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

    def call(prompt: str, want: dict) -> dict:
        body = client.request(prompt, want, model=cfg["model"])
        reply = api.chat.completions.create(**body)
        return client.parse(reply.choices[0].message.content or "", want)

    return call


def _one_document(path: Path, text: str, date: str | None, caller) -> tuple[list[dict], list[str]]:
    """Pass 1 for one document: the records that survive local checks."""
    reply = caller(_EXTRACT_PROMPT.format(path=path, body=text), EXTRACT_SCHEMA)
    raw = reply.get("records", [])
    kept: list[dict] = []
    notes: list[str] = []

    for record in raw:
        anchor = record.get("anchor", "")
        line = extract.anchor_line(anchor, text)
        if line is None:
            notes.append(f"{path}: dropped a record, its anchor quotes no line "
                         f"in the document: {anchor[:60]!r}")
            continue

        scope = list(record.get("scope") or [])
        bad = schema.invalid_scope(scope)
        if bad:
            notes.append(f"{path}: dropped {len(bad)} scope entr"
                         f"{'y' if len(bad) == 1 else 'ies'} that name no file")
            scope = [item for item in scope if item not in bad]

        try:
            item = schema.proposal(
                kind=record.get("kind", ""),
                text=record.get("text", ""),
                anchor=anchor,
                choice=record.get("choice", "") or "",
                rationale=record.get("rationale", "") or "",
                scope=scope,
                source={"path": str(path), "date": date},
                line=line,
            )
        except schema.SchemaError as exc:
            notes.append(f"{path}: dropped a record, {exc}")
            continue
        kept.append(item)

    matched, total = extract.match_rate(raw, text)
    notes.append(f"{path}: {matched}/{total} anchors matched")
    return kept, notes


def _link(proposals: list[dict], caller) -> tuple[list[dict], list[str]]:
    """Pass 2: the relations, validated locally before they are applied."""
    rows = json.dumps(link.payload(proposals), indent=2)
    reply = caller(_LINK_PROMPT.format(rows=rows), LINK_SCHEMA)
    edges, dropped = link.validate(reply.get("edges", []), proposals)
    notes = [f"link: dropped {edge}" for edge in dropped]
    notes.append(f"link: kept {len(edges)} edge{'' if len(edges) == 1 else 's'}")
    return link.apply(edges, proposals), notes


def two_pass(paths: list[str], jobs: int = 8, dry_run: bool = False,
             caller=None) -> tuple[list[dict], list[str]]:
    """Both passes over the given documents.

    A document whose call fails costs only its own records. One provider error
    out of 180 should not discard the other 179.
    """
    found = documents(paths)
    if not found:
        raise RunError(f"no markdown found under {', '.join(paths)}")

    report = [f"read {len(found)} document{'' if len(found) == 1 else 's'}"]
    if dry_run:
        report.extend(f"  would read {path}" for path in found[:20])
        if len(found) > 20:
            report.append(f"  ... and {len(found) - 20} more")
        return [], report

    caller = caller or _default_caller()
    git = extract.git_dates(Path.cwd())
    bodies = {path: path.read_text(errors="replace") for path in found}
    dates = {path: extract.resolve_date(str(path), bodies[path], git) for path in found}

    proposals: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {
            pool.submit(_one_document, path, bodies[path], dates[path], caller): path
            for path in found
        }
        for future in concurrent.futures.as_completed(futures):
            path = futures[future]
            try:
                kept, notes = future.result()
            except Exception as exc:
                report.append(f"{path}: extraction failed, {exc}")
                continue
            proposals.extend(kept)
            report.extend(notes)

    proposals.sort(key=lambda item: (item["source"]["path"], item.get("line", 0)))

    if len(proposals) < 2:
        report.append("link: skipped, nothing to relate")
        return proposals, report

    try:
        proposals, notes = _link(proposals, caller)
    except Exception as exc:
        report.append(f"link: failed, {exc}; proposals staged without relations")
        return proposals, report
    report.extend(notes)
    return proposals, report
