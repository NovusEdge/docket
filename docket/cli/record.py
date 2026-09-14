import argparse
import json
import sys

from docket import env
from docket.ledger import LedgerError, append, make_record, reasoning_hints


def _shared_fields(args: argparse.Namespace) -> dict:
    from docket.ledger import parse_evidence

    return {
        "scope": args.scope or [],
        "rationale": args.rationale or "",
        "supports": [
            [ref.strip() for ref in group.split(",") if ref.strip()]
            for group in (args.supports or [])
        ],
        "depends_on": [ref.strip() for ref in (args.depends_on or "").split(",") if ref.strip()],
        "answers": [ref.strip() for ref in (args.answers or "").split(",") if ref.strip()],
        "supersedes": [ref.strip() for ref in (args.supersedes or "").split(",") if ref.strip()],
        "evidence": [parse_evidence(item) for item in (args.evidence or [])],
        "revisit": args.revisit or "",
        "cost_if_wrong": args.cost or "",
        "pinned": bool(args.pin),
        "author": env.resolved_author(),
        "session": env.session_id(),
        "branch": env.branch(env.project_root()),
    }


def _append_cli(kind: str, args: argparse.Namespace) -> int:
    try:
        fields = _shared_fields(args)
        if kind == "decision":
            fields.update(
                {
                    "state": args.state,
                    "choice": args.choice,
                    "alternatives": args.alternative or [],
                    "decided_by": args.decided_by,
                }
            )
        elif kind == "claim":
            fields["state"] = args.state
        entry = make_record(kind, args.text, **fields)
        entry["id"] = ""
        entry = append(env.ledger_path(), entry)
    except (LedgerError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{entry['id']}  {entry['state']}  {entry['text']}")
    # Hints go to stderr so a caller piping the record line is unaffected.
    for hint in reasoning_hints(entry):
        print(f"docket: {entry['id']}: {hint}", file=sys.stderr)
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    return _append_cli("claim", args)


def cmd_decision(args: argparse.Namespace) -> int:
    return _append_cli("decision", args)


def cmd_question(args: argparse.Namespace) -> int:
    return _append_cli("question", args)
