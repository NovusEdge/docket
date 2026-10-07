import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.ledger as ledger


def claim(ident, **kwargs):
    kwargs.setdefault("state", "accepted")
    return ledger.make_record(
        "claim", f"Claim {ident} holds.", author="test", record_id=ident, **kwargs
    )


def correction(ident, target, fields):
    return {
        "schema": ledger.SCHEMA,
        "kind": "correction",
        "id": ident,
        "corrects": target,
        "fields": fields,
        "reason": "",
        "ts": "2026-10-02T00:00:00+00:00",
        "author": "test",
        "session": "",
        "branch": "",
    }


class SupersedeReasonTests(unittest.TestCase):
    def test_a_reason_is_recorded_with_supersedes(self):
        entries = ledger.validate_entries(
            [claim("c1"), claim("c2", supersedes=["c1"], supersede_reason="restate")]
        )
        self.assertEqual(entries[1]["supersede_reason"], "restate")

    def test_no_reason_leaves_the_field_absent(self):
        entries = ledger.validate_entries([claim("c1"), claim("c2", supersedes=["c1"])])
        self.assertNotIn("supersede_reason", entries[1])

    def test_a_reason_without_supersedes_is_refused(self):
        with self.assertRaisesRegex(ledger.LedgerError, "supersede_reason needs supersedes"):
            claim("c1", supersede_reason="restate")

    def test_an_unknown_reason_is_refused(self):
        with self.assertRaisesRegex(ledger.LedgerError, "supersede_reason must be one of"):
            ledger.validate_entries(
                [claim("c1"), claim("c2", supersedes=["c1"], supersede_reason="rewrite")]
            )

    def test_a_correction_can_relabel_the_reason(self):
        entries = ledger.project(
            [
                claim("c1"),
                claim("c2", supersedes=["c1"]),
                correction("c2.1", "c2", {"supersede_reason": "restate"}),
            ]
        )
        record = next(e for e in entries if e["id"] == "c2")
        self.assertEqual(record["supersede_reason"], "restate")

    def test_a_correction_cannot_add_a_reason_without_supersedes(self):
        with self.assertRaisesRegex(ledger.LedgerError, "supersede_reason needs supersedes"):
            ledger.validate_entries(
                [claim("c1"), correction("c1.1", "c1", {"supersede_reason": "restate"})]
            )


if __name__ == "__main__":
    unittest.main()
