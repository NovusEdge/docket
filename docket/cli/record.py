import argparse
import json
import sys
from typing import Any

from docket import env
from docket.ledger import LedgerError, append, append_many, make_record, reasoning_hints

# The fields a batch line may set. author, session and branch come from the
# environment, as they do for a single record; id is allocated under the lock.
_BATCH_FIELDS = frozenset(
    {
        "kind",
        "text",
        "state",
        "choice",
        "alternatives",
        "scope",
        "rationale",
        "supports",
        "depends_on",
        "answers",
        "supersedes",
        "supersede_reason",
        "evidence",
        "revisit",
        "cost_if_wrong",
        "pinned",
        "decided_by",
    }
)


def _ids(values: list[str] | None) -> list[str]:
    """Every ID from a repeatable flag whose values may also be comma lists."""
    return [ref.strip() for value in values or () for ref in value.split(",") if ref.strip()]


def _provenance() -> dict[str, str]:
    return {
        "author": env.resolved_author(),
        "session": env.session_id(),
        "branch": env.branch(env.project_root()),
    }


def _shared_fields(args: argparse.Namespace) -> dict:
    from docket.ledger import parse_evidence

    return {
        "scope": args.scope or [],
        "rationale": args.rationale or "",
        "supports": [
            [ref.strip() for ref in group.split(",") if ref.strip()]
            for group in (args.supports or [])
        ],
        "depends_on": _ids(getattr(args, "depends_on", None)),
        "answers": _ids(getattr(args, "answers", None)),
        "supersedes": _ids(args.supersedes),
        "supersede_reason": args.supersede_reason,
        "evidence": [parse_evidence(item) for item in (args.evidence or [])],
        "revisit": args.revisit or "",
        "cost_if_wrong": args.cost or "",
        "pinned": bool(args.pin),
        **_provenance(),
    }


def _report(entries: list[dict[str, Any]], *, as_json: bool, dry_run: bool) -> None:
    for entry in entries:
        if as_json or dry_run:
            print(json.dumps(entry, ensure_ascii=False))
        else:
            print(f"{entry['id']}  {entry['state']}  {entry['text']}")
        # Hints go to stderr so a caller piping the record line is unaffected.
        for hint in reasoning_hints(entry):
            print(f"docket: {entry['id']}: {hint}", file=sys.stderr)
        if entry["supersedes"] and "supersede_reason" not in entry and entry["kind"] != "question":
            print(
                f"docket: {entry['id']}: recorded as revise; records citing "
                f"{', '.join(entry['supersedes'])} will owe review. Pass --supersede-reason "
                "restate if only wording or links changed.",
                file=sys.stderr,
            )
    if dry_run:
        print(
            f"docket: dry run; {len(entries)} record(s) validated, nothing written", file=sys.stderr
        )


def _append_cli(kind: str, args: argparse.Namespace) -> int:
    try:
        if args.supersede_reason and not args.supersedes:
            raise LedgerError("docket: --supersede-reason needs --supersedes")
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
        entry = append(env.ledger_path(), entry, dry_run=args.dry_run)
    except (LedgerError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _report([entry], as_json=args.json, dry_run=args.dry_run)
    return 0


def _batch_record(line_number: int, value: Any) -> dict[str, Any]:
    from docket.ledger import parse_evidence

    where = f"docket: line {line_number}"
    if not isinstance(value, dict):
        raise LedgerError(f"{where}: each line must be a JSON object")
    unknown = sorted(set(value) - _BATCH_FIELDS)
    if unknown:
        raise LedgerError(f"{where}: unknown field(s): {', '.join(unknown)}")
    fields: dict[str, Any] = {k: v for k, v in value.items() if k not in ("kind", "text")}
    fields["evidence"] = [
        parse_evidence(item) if isinstance(item, str) else item
        for item in fields.get("evidence") or []
    ]
    fields.update(_provenance())
    try:
        # make_record checks shape only; relation targets, @N included, are
        # resolved and checked by append_many against the ledger.
        record = make_record(str(value.get("kind", "")), value.get("text", ""), **fields)
    except (LedgerError, TypeError) as exc:
        raise LedgerError(f"{where}: {str(exc).removeprefix('docket: ')}") from exc
    record["id"] = ""
    return record


def cmd_record(args: argparse.Namespace) -> int:
    try:
        if args.file == "-":
            text = sys.stdin.read()
        else:
            with open(args.file, encoding="utf-8") as handle:
                text = handle.read()
        records = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"docket: line {number}: invalid JSON: {exc.msg}") from exc
            records.append(_batch_record(number, value))
        if not records:
            raise LedgerError("docket: record: no records in the input")
        written = append_many(env.ledger_path(), records, dry_run=args.dry_run)
    except (LedgerError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _report(written, as_json=args.json, dry_run=args.dry_run)
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    return _append_cli("claim", args)


def cmd_decision(args: argparse.Namespace) -> int:
    return _append_cli("decision", args)


def cmd_question(args: argparse.Namespace) -> int:
    return _append_cli("question", args)
