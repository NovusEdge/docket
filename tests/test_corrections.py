import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.ledger as ledger
from docket import corrections
from docket.context_model import _revision


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
            ledger.validate_entries(
                [decision("d1"), decision("d2"), line("d1.1", "d2", {"scope": []})]
            )

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

    def test_decision_only_field_has_its_own_message(self):
        with self.assertRaisesRegex(ledger.LedgerError, "alternatives is a decision-only field"):
            ledger.validate_entries([claim("c1"), line("c1.1", "c1", {"alternatives": ["x"]})])

    def test_a_fixed_field_keeps_the_supersede_message(self):
        with self.assertRaisesRegex(ledger.LedgerError, "supersede the record"):
            ledger.validate_entries([decision("d1"), line("d1.1", "d1", {"choice": "Postgres"})])

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
            ledger.validate_entries([decision("d1"), line("d1.1", "d1", {"scope": []}, note="x")])

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
                [
                    decision("d1"),
                    line("d1.2", "d1", {"scope": []}),
                    line("d1.1", "d1", {"scope": []}),
                ]
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


class ProjectionTests(unittest.TestCase):
    def test_corrections_apply_in_file_order_and_the_lines_disappear(self):
        projected = ledger.project(
            [
                decision("d1", scope=["lib/a.py"]),
                line("d1.1", "d1", {"scope": ["docket/a.py"], "rationale": "First."}),
                line("d1.2", "d1", {"rationale": "Second."}),
            ]
        )
        self.assertEqual([item["id"] for item in projected], ["d1"])
        record = projected[0]
        self.assertEqual(record["scope"], ["docket/a.py"])
        self.assertEqual(record["rationale"], "Second.")
        self.assertEqual(record["corrections"], ["d1.1", "d1.2"])
        self.assertEqual(record["original"], {"scope": ["lib/a.py"], "rationale": ""})

    def test_an_empty_list_clears_a_field(self):
        projected = ledger.project(
            [decision("d1", scope=["a.py"]), line("d1.1", "d1", {"scope": []})]
        )
        self.assertEqual(projected[0]["scope"], [])

    def test_an_uncorrected_record_gains_no_keys(self):
        records = [decision("d1"), claim("c2")]
        before = ledger.project(records)
        after = ledger.project(records + [line("c2.1", "c2", {"revisit": "Later."})])
        self.assertNotIn("corrections", after[0])
        self.assertNotIn("original", after[0])
        self.assertEqual(_revision(before[:1]), _revision(after[:1]))

    def test_a_correction_of_a_retired_record_keeps_it_retired(self):
        projected = ledger.project(
            [
                decision("d1"),
                decision("d2", supersedes=["d1"]),
                line("d1.1", "d1", {"rationale": "Latency."}),
            ]
        )
        self.assertEqual(projected[0]["retired_by"], "d2")
        self.assertEqual(projected[0]["rationale"], "Latency.")

    def test_a_pin_correction_changes_the_pin(self):
        projected = ledger.project([claim("c1"), line("c1.1", "c1", {"pinned": True})])
        self.assertTrue(projected[0]["pinned"])

    def test_graph_payload_carries_the_corrected_text(self):
        payload = ledger.graph_payload(
            [decision("d1"), line("d1.1", "d1", {"text": "The cache lives in Valkey."})]
        )
        self.assertEqual(payload["entries"][0]["question"], "The cache lives in Valkey.")


class AppendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, kind, text, **kwargs):
        return ledger.append(self.path, ledger.make_record(kind, text, author="test", **kwargs))

    def correct(self, target, fields):
        return ledger.append(self.path, corrections.make(target, fields, author="test"))

    def test_append_numbers_corrections_per_record(self):
        self.add("decision", "The cache lives in Redis.", choice="Redis")
        self.add("claim", "Writes are durable.")
        self.assertEqual(self.correct("d1", {"scope": ["a"]})["id"], "d1.1")
        self.assertEqual(self.correct("c2", {"scope": ["a"]})["id"], "c2.1")
        self.assertEqual(self.correct("d1", {"scope": ["b"]})["id"], "d1.2")
        self.assertEqual(self.add("claim", "Another.")["id"], "c3")

    def test_concurrent_corrections_never_share_a_number(self):
        self.add("claim", "Writes are durable.")
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda n: self.correct("c1", {"revisit": str(n)})["id"], range(8)))
        self.assertEqual(sorted(ids), sorted(f"c1.{n}" for n in range(1, 9)))

    def test_question_shaped_text_is_refused(self):
        self.add("decision", "The cache lives in Redis.", choice="Redis")
        with self.assertRaisesRegex(ledger.LedgerError, "not ask it"):
            self.correct("d1", {"text": "Where does the cache live?"})
        self.assertEqual([item["id"] for item in ledger.read(self.path)], ["d1"])

    def test_text_that_restates_the_choice_is_refused(self):
        self.add("decision", "The cache lives in Redis.", choice="Redis")
        with self.assertRaisesRegex(ledger.LedgerError, "more than the choice"):
            self.correct("d1", {"text": "Redis"})

    def test_a_rationale_that_echoes_the_choice_is_refused(self):
        self.add("decision", "The cache lives in Redis.", choice="Redis")
        with self.assertRaisesRegex(ledger.LedgerError, "say why"):
            self.correct("d1", {"rationale": "redis"})

    def write_echoing_decision(self):
        # Records written before the echo rule carry rationale == choice.
        record = ledger.make_record(
            "decision", "The cache lives in Redis.", choice="Redis", author="test"
        )
        record["rationale"] = "Redis"
        record["alternatives"] = ["Redis"]
        ledger.append(self.path, record)

    def test_scope_correction_ignores_an_old_rationale_echo(self):
        self.write_echoing_decision()
        self.assertEqual(self.correct("d1", {"scope": ["docket/env.py"]})["id"], "d1.1")

    def test_text_correction_ignores_an_old_rationale_echo(self):
        self.write_echoing_decision()
        self.assertEqual(self.correct("d1", {"text": "The cache lives in Valkey."})["id"], "d1.1")

    def test_a_text_correction_that_equals_the_rationale_is_refused(self):
        self.add("decision", "The cache lives in Redis.", choice="Redis", rationale="It is fast.")
        with self.assertRaisesRegex(ledger.LedgerError, "say why"):
            self.correct("d1", {"text": "It is fast."})

    def test_alternatives_that_only_repeat_the_choice_are_refused(self):
        self.add("decision", "The cache lives in Redis.", choice="Redis")
        with self.assertRaisesRegex(ledger.LedgerError, "option the choice beat"):
            self.correct("d1", {"alternatives": ["redis"]})

    def test_a_correction_refusal_checks_the_corrected_state(self):
        self.add("decision", "The cache lives in Redis.", choice="Redis")
        self.correct("d1", {"rationale": "It is fast."})
        with self.assertRaisesRegex(ledger.LedgerError, "say why"):
            self.correct("d1", {"text": "It is fast."})

    def test_a_no_op_field_is_refused(self):
        self.add("claim", "Writes are durable.", pinned=True)
        with self.assertRaisesRegex(ledger.LedgerError, "nothing to correct"):
            self.correct("c1", {"pinned": True})

    def test_a_no_op_alongside_a_real_change_writes_only_the_real_field(self):
        self.add("claim", "Writes are durable.", scope=["a.py"])
        entry = self.correct("c1", {"scope": ["a.py"], "revisit": "Later."})
        self.assertEqual(entry["fields"], {"revisit": "Later."})

    def test_a_pre_numbered_correction_skips_the_write_time_refusals(self):
        self.add("decision", "The cache lives in Redis.", choice="Redis")
        pre_numbered = corrections.make("d1", {"text": "Redis"}, author="test")
        pre_numbered["id"] = "d1.1"
        entry = ledger.append(self.path, pre_numbered)
        self.assertEqual(entry["id"], "d1.1")


if __name__ == "__main__":
    unittest.main()
