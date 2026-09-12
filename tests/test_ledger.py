import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import docket_ledger as ledger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, kind, text, **kwargs):
        return ledger.append(self.path, ledger.make_record(kind, text, author="test", **kwargs))

    def test_ids_share_one_sequence_across_kinds(self):
        self.assertEqual(self.add("claim", "one")["id"], "c1")
        self.assertEqual(self.add("question", "two")["id"], "q2")
        self.assertEqual(self.add("decision", "three", choice="yes")["id"], "d3")

    def test_invalid_state_kind_and_references_are_rejected(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.make_record("claim", "bad", state="adopted")
        self.add("claim", "premise")
        with self.assertRaisesRegex(ledger.LedgerError, "unknown or later"):
            self.add("decision", "pick", choice="yes", depends_on=["c99"])
        with self.assertRaisesRegex(ledger.LedgerError, "not a question"):
            self.add("claim", "answer", answers=["c1"])

    def test_global_numeric_sequence_is_unique_and_increasing(self):
        first = ledger.make_record("claim", "first", author="test", record_id="c2")
        second = ledger.make_record("decision", "second", choice="yes", author="test", record_id="d1")
        with self.assertRaisesRegex(ledger.LedgerError, "monotonically"):
            ledger.validate_entries([first, second])

    def test_unknown_fields_and_invalid_falsy_shapes_are_rejected(self):
        for field, value in (("scope", ""), ("supports", ""), ("depends_on", ""),
                             ("answers", ""), ("supersedes", ""), ("evidence", "")):
            with self.assertRaises(ledger.LedgerError, msg=field):
                ledger.make_record("claim", "invalid", author="test", **{field: value})
        claim = ledger.make_record("claim", "claim", author="test", record_id="c1")
        claim["depend_on"] = []
        with self.assertRaisesRegex(ledger.LedgerError, "unknown field"):
            ledger.validate_record(claim)
        with self.assertRaisesRegex(ledger.LedgerError, "decision-only"):
            ledger.make_record("claim", "claim", author="test", decided_by="someone")

    def test_legacy_audit_metadata_has_a_strict_shape(self):
        claim = ledger.make_record("claim", "claim", author="test", record_id="c1")
        claim["legacy"] = {"source_id": "d1", "raw": {"id": "d1"}, "relation_map": {
            "source_because": [], "source_depends_on": [], "source_answers": [],
            "source_supersedes": [], "mapped_supports": [], "mapped_depends_on": [],
            "mapped_answers": [], "mapped_supersedes": [], "overrides": []}}
        self.assertEqual(ledger.validate_record(claim)["legacy"]["source_id"], "d1")
        claim["legacy"]["relation_map"]["mapped_answers"] = ["q99"]
        with self.assertRaisesRegex(ledger.LedgerError, "mapped relations"):
            ledger.validate_record(claim)
        claim["legacy"]["relation_map"]["mapped_answers"] = []
        claim["legacy"]["raw"] = "not an object"
        with self.assertRaisesRegex(ledger.LedgerError, "raw/relation_map"):
            ledger.validate_record(claim)

    def test_supersession_and_resolution_are_derived(self):
        question = self.add("question", "which?")
        claim = self.add("claim", "yes", state="accepted", answers=[question["id"]])
        projected = ledger.project(ledger.read(self.path))
        self.assertEqual({entry["id"]: entry for entry in projected}[question["id"]]["state"], "resolved")
        replacement = self.add("claim", "better", state="accepted", supersedes=[claim["id"]])
        projected = ledger.project(ledger.read(self.path))
        by_id = {entry["id"]: entry for entry in projected}
        self.assertEqual(by_id[claim["id"]]["retired_by"], replacement["id"])
        self.assertEqual(by_id[question["id"]]["state"], "open")
        self.assertEqual(by_id[question["id"]]["recorded_state"], "open")
        with self.assertRaisesRegex(ledger.LedgerError, "already retired"):
            self.add("claim", "third", supersedes=[claim["id"]])

    def test_decision_applicability_and_blockers(self):
        premise = self.add("claim", "premise", state="unassessed")
        decision = self.add("decision", "pick", choice="yes", depends_on=[premise["id"]])
        projected = {entry["id"]: entry for entry in ledger.project(ledger.read(self.path))}
        self.assertFalse(projected[decision["id"]]["applicable"])
        self.assertEqual(projected[decision["id"]]["blocked_by"], [premise["id"]])

    def test_corrupt_and_schema_one_files_fail_loudly(self):
        self.path.write_text("not json\n")
        with self.assertRaisesRegex(ledger.LedgerError, "invalid JSON"):
            ledger.read(self.path)
        self.path.write_text(json.dumps({"schema": 1}) + "\n")
        with self.assertRaisesRegex(ledger.LedgerError, "migrate"):
            ledger.read(self.path)

    def test_append_repairs_missing_final_newline_without_merging_records(self):
        first = ledger.make_record("claim", "one", author="test")
        first["id"] = "c1"
        self.path.write_text(json.dumps(first))
        second = ledger.append(self.path, ledger.make_record("question", "two", author="test"))
        self.assertEqual(second["id"], "q2")
        self.assertEqual([entry["id"] for entry in ledger.read(self.path)], ["c1", "q2"])

    def test_concurrent_appends_keep_global_ids_unique(self):
        def write(index):
            kind = ("claim", "question", "decision")[index % 3]
            kwargs = {"choice": "yes"} if kind == "decision" else {}
            return self.add(kind, f"record {index}", **kwargs)["id"]

        with ThreadPoolExecutor(max_workers=8) as workers:
            ids = list(workers.map(write, range(18)))
        self.assertEqual(len(set(ids)), 18)
        self.assertEqual({int(item[1:]) for item in ids}, set(range(1, 19)))


if __name__ == "__main__":
    unittest.main()
