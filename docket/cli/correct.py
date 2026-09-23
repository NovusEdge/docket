import argparse
import sys

from docket import corrections, env
from docket.ledger import LedgerError, append, parse_evidence

# Flags that change what a record commits to. Accepted by the parser only so
# the refusal can name supersession instead of argparse's generic error.
FIXED_FLAGS = {
    "choice": "--choice",
    "state": "--state",
    "supports": "--supports",
    "depends_on": "--depends-on",
    "answers": "--answers",
    "supersedes": "--supersedes",
}
CLEARABLE = ("scope", "evidence", "alternatives")


def _fields(args: argparse.Namespace) -> dict:
    fields: dict = {}
    if args.text is not None:
        fields["text"] = args.text
    if args.rationale is not None:
        fields["rationale"] = args.rationale
    if args.scope:
        fields["scope"] = args.scope
    if args.evidence:
        fields["evidence"] = [parse_evidence(item) for item in args.evidence]
    if args.revisit is not None:
        fields["revisit"] = args.revisit
    if args.cost is not None:
        fields["cost_if_wrong"] = args.cost
    if args.pin:
        fields["pinned"] = True
    if args.unpin:
        fields["pinned"] = False
    if args.alternative:
        fields["alternatives"] = args.alternative
    if args.decided_by is not None:
        fields["decided_by"] = args.decided_by
    for name in args.clear:
        if name in fields:
            raise LedgerError(f"docket: --clear {name} and --{name} conflict")
        fields[name] = []
    return fields


def cmd_correct(args: argparse.Namespace) -> int:
    fixed = [flag for dest, flag in FIXED_FLAGS.items() if getattr(args, dest) is not None]
    if fixed:
        print(
            f"docket: a correction cannot change {', '.join(fixed)}; record a "
            f"restatement with --supersedes {args.id} instead",
            file=sys.stderr,
        )
        return 1
    try:
        fields = _fields(args)
        if not fields:
            raise LedgerError("docket: name at least one field to correct")
        entry = append(
            env.ledger_path(),
            corrections.make(
                args.id,
                fields,
                reason=args.reason,
                author=env.resolved_author(),
                session=env.session_id(),
                branch=env.branch(env.project_root()),
            ),
        )
    except LedgerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{entry['id']}  corrects {entry['corrects']}: {', '.join(sorted(fields))}")
    return 0


def add_correct_parser(sub) -> None:
    co = sub.add_parser("correct", help="fix a record's wording or metadata, keeping its id")
    co.add_argument("id", help="the claim, decision, or question to correct")
    co.add_argument("--text")
    co.add_argument("--rationale")
    co.add_argument("--scope", action="append", default=[])
    co.add_argument("--evidence", action="append", default=[])
    co.add_argument("--revisit")
    co.add_argument("--cost")
    pin = co.add_mutually_exclusive_group()
    pin.add_argument("--pin", action="store_true")
    pin.add_argument("--unpin", action="store_true")
    co.add_argument("--alternative", action="append", default=[])
    co.add_argument("--decided-by")
    co.add_argument(
        "--clear", action="append", default=[], choices=CLEARABLE, help="set a list field to empty"
    )
    co.add_argument("--reason", default="", help="why the record was wrong")
    for dest, flag in FIXED_FLAGS.items():
        co.add_argument(flag, dest=dest, help=argparse.SUPPRESS)
    co.set_defaults(func=cmd_correct)
