"""Accepted proposals becoming ledger records.

The only place construct touches the ledger, and it writes through the ordinary
writer so numbering and locking stay honest. Acceptance is the approval the
ledger exists to record; extraction never is.
"""

from __future__ import annotations

from pathlib import Path

from docket.construct import stage
from docket.ledger import append, make_record

AUTHOR = "docket-construct"


def _chronological(proposals: list[dict]) -> list[dict]:
    """Oldest document first.

    The briefing scores recency from the numeric record id, never from `ts`, so
    the order records enter the ledger is the only thing that makes a newer
    decision outrank an older one. A run that accepts in staging order leaves
    887 records the walker cannot tell apart by age.

    An undated document sorts first: it has established no recency to claim.
    """
    return sorted(proposals, key=lambda item: (item["source"]["date"] or "",))


def _timestamp(date: str | None) -> str | None:
    """The document's date as a record timestamp, or None to stamp the run.

    Provenance, not ranking. A record stamped with the run date tells a later
    reader that a decision from April was made the day construct read it.
    """
    return f"{date}T00:00:00+00:00" if date else None


def _order(proposals: list[dict]) -> list[dict]:
    """Supported records first, so a key resolves to an id by the time it is
    needed. Support is acyclic by then, so a stable pass suffices.

    Date order survives wherever support does not constrain it, because the
    walk keeps its input order and only pulls grounds forward.
    """
    by_key = {p["key"]: p for p in proposals}
    done: list[dict] = []
    seen: set[str] = set()

    def visit(item: dict) -> None:
        if item["key"] in seen:
            return
        seen.add(item["key"])
        for group in item.get("supports") or []:
            for key in group:
                if key in by_key:
                    visit(by_key[key])
        for key in item.get("supersedes") or []:
            if key in by_key:
                visit(by_key[key])
        done.append(item)

    for item in proposals:
        visit(item)
    return done


def _rationale(item: dict) -> str:
    """The record's own rationale, with the document it was read from.

    A later reader has to be able to tell a constructed record from one a human
    wrote at the time.
    """
    source = item["source"]["path"]
    body = (item.get("rationale") or "").strip()
    note = f"Constructed from {source}."
    return f"{body} {note}".strip()


def run(staged: Path, ledger: Path, source: str | None = None) -> tuple[int, int]:
    """Write every accepted proposal, and report written and skipped counts.

    Incremental and resumable: each proposal carries its own state, so
    accepting one document's records leaves the rest staged. A 520-record
    review spans several sittings, and a run that must finish in one pass gets
    rubber-stamped instead of read.
    """
    proposals = stage.read(staged)
    wanted = [p for p in proposals
              if p.get("state") == "accepted"
              and (source is None or p["source"]["path"] == source)]

    ids: dict[str, str] = {}
    written = skipped = 0

    for item in _order(_chronological(wanted)):
        supports = []
        dropped = False
        for group in item.get("supports") or []:
            resolved = [ids[key] for key in group if key in ids]
            if len(resolved) != len(group):
                # A record supporting one nobody accepted would enter the
                # ledger claiming grounds that are not there.
                dropped = True
                break
            if resolved:
                supports.append(resolved)
        if dropped:
            skipped += 1
            continue

        supersedes = [ids[key] for key in item.get("supersedes") or [] if key in ids]

        record = make_record(
            item["kind"],
            item["text"],
            choice=item.get("choice") or None,
            scope=list(item.get("scope") or []),
            rationale=_rationale(item),
            supports=supports or None,
            supersedes=supersedes or None,
            author=AUTHOR,
            ts=_timestamp(item["source"]["date"]),
        )
        stored = append(ledger, record)
        ids[item["key"]] = stored["id"]
        item["state"] = "written"
        written += 1
        # After each append, never once at the end. There is no transaction
        # across N appends, so a failure on append k would otherwise commit k-1
        # records while the stage still calls them accepted. The user would see
        # the error, rerun, and append a second copy of every one.
        stage.write(staged, proposals)

    return written, skipped
