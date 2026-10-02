import argparse
import sys

from docket import env, reviews
from docket.ledger import ID_RE, LedgerError, append


def cmd_review(args: argparse.Namespace) -> int:
    if not ID_RE.fullmatch(args.id):
        print("docket: review names a claim or decision id", file=sys.stderr)
        return 1
    try:
        entry = append(
            env.ledger_path(),
            reviews.make(
                args.id,
                note=args.note,
                author=env.resolved_author(),
                session=env.session_id(),
                branch=env.branch(env.project_root()),
            ),
        )
    except (LedgerError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    pairs = ", ".join(f"{ground} -> {head}" for ground, head in entry["grounds"].items())
    print(f"{entry['id']}  reviews {entry['reviews']}: {pairs}")
    return 0


def add_review_parser(sub) -> None:
    rv = sub.add_parser("review", help="acknowledge that a flagged record still stands")
    rv.add_argument("id", help="the claim or decision to review")
    rv.add_argument("--note", default="", help="what the review concluded")
    rv.set_defaults(func=cmd_review)
