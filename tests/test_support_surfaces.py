import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.ledger as ledger
from docket import where
from docket.context import build_context
from docket.context_delta import build_delta


def claim(ident, **kwargs):
    kwargs.setdefault("state", "accepted")
    return ledger.make_record(
        "claim", f"Claim {ident} holds.", author="test", record_id=ident, **kwargs
    )


FLAGGED = [claim("c1"), claim("c2", supports=[["c1"]]), claim("c3", supersedes=["c1"])]
LOST = [
    claim("c1"),
    claim("c2", supports=[["c1"]]),
    claim("c3", supersedes=["c1"], supersede_reason="reverse"),
]


class WhereTests(unittest.TestCase):
    def ids(self, entries, query):
        q = where.parse(query)
        return [e["id"] for e in ledger.project(entries) if q.matches(e)]

    def test_is_flagged(self):
        self.assertEqual(self.ids(FLAGGED, "is:flagged"), ["c2"])

    def test_is_unsupported(self):
        self.assertEqual(self.ids(LOST, "is:unsupported"), ["c2"])


class BriefingTests(unittest.TestCase):
    def test_a_flagged_record_renders_review_owed_and_the_footer_counts_it(self):
        text = build_context(ledger.project(FLAGGED), all_records=True)
        self.assertIn('review_owed: [{"because": "revise", "ground": "c1", "head": "c3"}]', text)
        self.assertIn("# owe review: 1; docket list --where is:flagged", text)

    def test_an_unsupported_record_renders_lost(self):
        text = build_context(ledger.project(LOST), all_records=True)
        self.assertIn('lost: [{"because": "reverse", "ground": "c1"}]', text)

    def test_an_unsupported_prerequisite_does_not_block_its_dependent(self):
        entries = LOST + [
            ledger.make_record(
                "decision",
                "Ship it.",
                author="test",
                record_id="d4",
                state="adopted",
                choice="ship",
                depends_on=["c2"],
            )
        ]
        text = build_context(ledger.project(entries), all_records=True)
        self.assertNotIn("applicable:", text)
        self.assertNotIn("blocked:", text)


def decision(ident, depends_on, **kwargs):
    return ledger.make_record(
        "decision",
        "Ship it.",
        author="test",
        record_id=ident,
        state="adopted",
        choice="ship",
        depends_on=depends_on,
        **kwargs,
    )


class BlockedLineTests(unittest.TestCase):
    def blocked(self, entries):
        text = build_context(ledger.project(entries), all_records=True)
        return [line for line in text.splitlines() if line.startswith("blocked:")]

    def test_a_restated_prerequisite_is_followed_to_its_head(self):
        entries = [
            claim("c1"),
            claim("c2", state="unassessed"),
            claim("c3", supersedes=["c1"], supersede_reason="restate"),
            decision("d4", ["c1", "c2"]),
        ]
        lines = self.blocked(entries)
        self.assertEqual(lines, ["blocked: c2 unassessed"])

    def test_a_revised_prerequisite_blocks_at_its_rejected_head(self):
        entries = [
            claim("c1"),
            claim("c3", state="rejected", supersedes=["c1"], supersede_reason="revise"),
            decision("d4", ["c1"]),
        ]
        self.assertEqual(self.blocked(entries), ["blocked: c3 rejected"])

    def test_a_reversed_prerequisite_blocks_at_the_recorded_prerequisite(self):
        entries = [
            claim("c1"),
            claim("c3", supersedes=["c1"], supersede_reason="reverse"),
            decision("d4", ["c1"]),
        ]
        self.assertEqual(self.blocked(entries), ["blocked: c1 reversed"])


class DeltaTests(unittest.TestCase):
    def test_an_already_unsupported_record_is_not_reported_again(self):
        entries = LOST + [claim("c4")]
        baseline = ledger.project(LOST)
        text = build_delta(ledger.project(entries), since="c3", baseline=baseline, raw=entries)
        self.assertIn("0 no longer available", text)

    def test_newly_flagged_records_are_reported(self):
        history = ledger.project(FLAGGED)
        baseline = ledger.project(FLAGGED[:2])
        text = build_delta(history, since="c2", baseline=baseline, raw=FLAGGED)
        self.assertIn("1 newly owe review", text)

    def test_a_record_that_became_unsupported_is_no_longer_available(self):
        history = ledger.project(LOST)
        baseline = ledger.project(LOST[:2])
        text = build_delta(history, since="c2", baseline=baseline, raw=LOST)
        self.assertIn("2 no longer available", text)
        self.assertIn("### c2 | claim | accepted [changed]", text)

    def test_a_stale_digest_falls_back(self):
        history = ledger.project(FLAGGED)
        baseline = ledger.project(FLAGGED[:2])
        self.assertIsNone(
            build_delta(history, since="c2@000000000000", baseline=baseline, raw=FLAGGED)
        )


if __name__ == "__main__":
    unittest.main()
