import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.ledger as ledger
from docket import corrections


def line(ident, target, fields, **extra):
    record = {
        "schema": 2,
        "kind": "correction",
        "id": ident,
        "corrects": target,
        "fields": fields,
        "reason": "",
        "ts": "2026-09-23T00:00:00+00:00",
        "author": "test",
        "session": "",
        "branch": "",
    }
    record.update(extra)
    return record


def decision(ident, text="The cache lives in Redis.", **kwargs):
    kwargs.setdefault("choice", "Redis")
    return ledger.make_record("decision", text, author="test", record_id=ident, **kwargs)


def claim(ident, text="Writes are durable.", **kwargs):
    return ledger.make_record("claim", text, author="test", record_id=ident, **kwargs)


class ValidationTests(unittest.TestCase):
    def test_a_correction_of_an_earlier_record_reads(self):
        entries = ledger.validate_entries([decision("d1"), line("d1.1", "d1", {"scope": ["a.py"]})])
        self.assertEqual(entries[1]["id"], "d1.1")

    def test_the_target_must_be_earlier(self):
        with self.assertRaisesRegex(ledger.LedgerError, "unknown or later"):
            ledger.validate_entries([line("d1.1", "d1", {"scope": []}), decision("d1")])

    def test_the_id_base_must_equal_corrects(self):
        with self.assertRaisesRegex(ledger.LedgerError, "must start with"):
            ledger.validate_entries([decision("d1"), decision("d2"), line("d1.1", "d2", {"scope": []})])

    def test_a_malformed_id_is_refused(self):
        with self.assertRaisesRegex(ledger.LedgerError, "<record id>.<n>"):
            ledger.validate_entries([decision("d1"), line("d1.0", "d1", {"scope": []})])

    def test_fixed_fields_are_refused(self):
        for field, value in (
            ("choice", "Postgres"),
            ("state", "revoked"),
            ("supports", [["c1"]]),
            ("supersedes", []),
            ("kind", "claim"),
            ("author", "someone"),
        ):
            with self.assertRaisesRegex(ledger.LedgerError, "supersede", msg=field):
                ledger.validate_entries([decision("d1"), line("d1.1", "d1", {field: value})])

    def test_decision_only_fields_are_refused_on_a_claim(self):
        with self.assertRaisesRegex(ledger.LedgerError, "alternatives"):
            ledger.validate_entries([claim("c1"), line("c1.1", "c1", {"alternatives": ["x"]})])

    def test_a_value_of_the_wrong_type_is_refused(self):
        with self.assertRaisesRegex(ledger.LedgerError, "scope"):
            ledger.validate_entries([decision("d1"), line("d1.1", "d1", {"scope": "a.py"})])
        with self.assertRaisesRegex(ledger.LedgerError, "pinned"):
            ledger.validate_entries([decision("d1"), line("d1.1", "d1", {"pinned": "yes"})])

    def test_empty_fields_are_refused(self):
        with self.assertRaisesRegex(ledger.LedgerError, "non-empty"):
            ledger.validate_entries([decision("d1"), line("d1.1", "d1", {})])

    def test_unknown_line_fields_are_refused(self):
        with self.assertRaisesRegex(ledger.LedgerError, "unknown field"):
            ledger.validate_entries(
                [decision("d1"), line("d1.1", "d1", {"scope": []}, note="x")]
            )

    def test_n_must_increase_per_target_and_gaps_are_allowed(self):
        ledger.validate_entries(
            [
                decision("d1"),
                decision("d2"),
                line("d1.1", "d1", {"scope": []}),
                line("d2.1", "d2", {"scope": []}),
                line("d1.3", "d1", {"scope": ["b"]}),
            ]
        )
        with self.assertRaisesRegex(ledger.LedgerError, "must increase"):
            ledger.validate_entries(
                [decision("d1"), line("d1.2", "d1", {"scope": []}), line("d1.1", "d1", {"scope": []})]
            )

    def test_a_retired_record_is_correctable(self):
        ledger.validate_entries(
            [
                decision("d1"),
                decision("d2", supersedes=["d1"]),
                line("d1.1", "d1", {"rationale": "Latency."}),
            ]
        )

    def test_nothing_may_point_at_a_correction(self):
        with self.assertRaisesRegex(ledger.LedgerError, "unknown or later"):
            ledger.validate_entries(
                [
                    claim("c1"),
                    line("c1.1", "c1", {"scope": []}),
                    decision("d2", supports=[["c1.1"]]),
                ]
            )

    def test_record_numbering_ignores_corrections(self):
        entries = ledger.validate_entries([decision("d1"), line("d1.1", "d1", {"scope": []})])
        self.assertEqual(ledger.allocate_id(entries, "claim"), "c2")


class ReadTests(unittest.TestCase):
    def test_read_returns_correction_lines_in_file_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            import json

            path.write_text(
                "\n".join(
                    json.dumps(item)
                    for item in (decision("d1"), line("d1.1", "d1", {"scope": ["a.py"]}))
                )
                + "\n"
            )
            self.assertEqual([item["id"] for item in ledger.read(path)], ["d1", "d1.1"])


if __name__ == "__main__":
    unittest.main()
