import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.ledger as ledger
from docket import rebase, reviews


def claim(ident, **kwargs):
    kwargs.setdefault("state", "accepted")
    return ledger.make_record(
        "claim", f"Claim {ident} holds.", author="test", record_id=ident, **kwargs
    )


def review(ident, target, grounds, note=""):
    return {
        "schema": 2,
        "kind": "review",
        "id": ident,
        "reviews": target,
        "grounds": grounds,
        "note": note,
        "ts": "2026-10-02T00:00:00+00:00",
        "author": "test",
        "session": "",
        "branch": "",
    }


BASE = [claim("c1"), claim("c2", supports=[["c1"]]), claim("c3", supersedes=["c1"])]


class ReviewValidationTests(unittest.TestCase):
    def test_a_review_reads(self):
        entries = ledger.validate_entries([*BASE, review("c2.r1", "c2", {"c1": "c3"})])
        self.assertEqual(entries[-1]["id"], "c2.r1")

    def test_the_id_base_must_equal_reviews(self):
        with self.assertRaisesRegex(ledger.LedgerError, "must start with"):
            ledger.validate_entries([*BASE, review("c3.r1", "c2", {"c1": "c3"})])

    def test_a_malformed_id_is_refused(self):
        with self.assertRaisesRegex(ledger.LedgerError, r"<record id>\.r<n>"):
            ledger.validate_entries([*BASE, review("c2.r0", "c2", {"c1": "c3"})])

    def test_grounds_must_be_a_nonempty_map_of_known_ids(self):
        for grounds in ({}, {"c1": "c9"}, {"c9": "c3"}, {"c1": 3}):
            with self.subTest(grounds=grounds):
                with self.assertRaises(ledger.LedgerError):
                    ledger.validate_entries([*BASE, review("c2.r1", "c2", grounds)])

    def test_numbers_increase_per_record(self):
        with self.assertRaisesRegex(ledger.LedgerError, "must increase"):
            ledger.validate_entries(
                [*BASE, review("c2.r2", "c2", {"c1": "c3"}), review("c2.r1", "c2", {"c1": "c3"})]
            )

    def test_unknown_fields_are_refused(self):
        line = review("c2.r1", "c2", {"c1": "c3"})
        line["extra"] = 1
        with self.assertRaisesRegex(ledger.LedgerError, "unknown field"):
            ledger.validate_entries([*BASE, line])

    def test_a_review_does_not_consume_a_record_number(self):
        entries = ledger.validate_entries([*BASE, review("c2.r1", "c2", {"c1": "c3"})])
        self.assertEqual(ledger.next_id(entries, "claim"), "4")


class ReviewFoldTests(unittest.TestCase):
    def test_fold_attaches_reviews_and_drops_the_lines(self):
        folded = reviews.fold(
            ledger.validate_entries([*BASE, review("c2.r1", "c2", {"c1": "c3"}, note="fine")])
        )
        self.assertEqual([e["id"] for e in folded], ["c1", "c2", "c3"])
        self.assertEqual(
            folded[1]["reviews"], [{"id": "c2.r1", "grounds": {"c1": "c3"}, "note": "fine"}]
        )
        self.assertNotIn("reviews", folded[0])


class ReviewAllocateTests(unittest.TestCase):
    def test_allocate_numbers_per_record(self):
        entries = [*BASE, review("c2.r1", "c2", {"c1": "c3"})]
        self.assertEqual(reviews.allocate(entries, "c2"), "c2.r2")
        self.assertEqual(reviews.allocate(entries, "c3"), "c3.r1")


class ReviewRebaseTests(unittest.TestCase):
    def test_rebase_renumbers_review_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            mine = Path(tmp) / "mine.jsonl"
            theirs = Path(tmp) / "theirs.jsonl"
            for path, extra in (
                (mine, [claim("c4")]),
                (theirs, [claim("c4", supports=[["c1"]]), review("c4.r1", "c4", {"c1": "c3"})]),
            ):
                for record in [*BASE, *extra]:
                    ledger.append(path, record)
            tail, mapping = rebase.renumber(ledger.read(mine), ledger.read(theirs))
            self.assertEqual(mapping["c4"], "c5")
            line = tail[-1]
            self.assertEqual((line["id"], line["reviews"]), ("c5.r1", "c5"))
            self.assertEqual(line["grounds"], {"c1": "c3"})


if __name__ == "__main__":
    unittest.main()
