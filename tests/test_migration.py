"""Tests for the explicit schema-1 to schema-2 migration tool."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docket import features, ledger
from docket import migrate as docket_migrate
from docket.ledger import SCHEMA, LedgerError, make_record
from docket.ledger import read as ledger_read


def load_migrator():
    return docket_migrate


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


class MigrationTests(unittest.TestCase):
    def source_records(self) -> list[dict]:
        return [
            {
                "id": "d1",
                "ts": "2026-01-01T00:00:00+00:00",
                "state": "settled",
                "question": "Use the typed ledger?",
                "answer": "Yes",
                "because": [],
                "supersedes": [],
                "cost_if_wrong": "migration",
                "session": "old-session",
                "author": "old-agent",
                "branch": "old-branch",
            },
            {
                "id": "d2",
                "ts": "2026-01-02T00:00:00+00:00",
                "state": "open",
                "question": "Which validator?",
                "answer": "Choose one later",
                "because": ["d1"],
                "supersedes": [],
                "cost_if_wrong": "",
                "session": "old-session",
                "author": "old-agent",
                "branch": "old-branch",
            },
            {
                "id": "d3",
                "ts": "2026-01-03T00:00:00+00:00",
                "state": "settled",
                "question": "Answer which validator?",
                "answer": "Core validator",
                "because": [["d1"], ["d2"]],
                "supersedes": ["d2"],
                "cost_if_wrong": "review",
                "session": "old-session",
                "author": "old-agent",
                "branch": "old-branch",
            },
        ]

    def mapping(self) -> dict:
        return {
            "d1": {
                "kind": "decision",
                "state": "adopted",
                "text": "Use the typed ledger?",
                "choice": "Yes",
                "alternatives": ["Yes", "No"],
            },
            "d2": {
                "kind": "question",
                "state": "open",
                "text": "Which validator?",
            },
            "d3": {
                "kind": "decision",
                "state": "adopted",
                "text": "Answer which validator?",
                "choice": "Core validator",
                # The source also cited a question.  Supports may only target
                # claims or decisions, so the map must explicitly treat it.
                "supports": [["d1"]],
                # d3's old supersession of a question is intentionally
                # converted to an answer relation, with retirement removed.
                "answers": ["d2"],
                "supersedes": [],
                "depends_on": ["d1"],
            },
        }

    def test_migrates_relations_and_retains_raw_provenance(self):
        migrator = load_migrator()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "old.jsonl"
            mapping = root / "map.json"
            output = root / "new.jsonl"
            write_jsonl(source, self.source_records())
            mapping.write_text(json.dumps(self.mapping()))

            migrator.migrate(source, mapping, output)

            records = [json.loads(line) for line in output.read_text().splitlines()]
            by_id = {record["id"]: record for record in records}
            self.assertEqual(by_id["q2"]["supports"], [["d1"]])
            self.assertEqual(by_id["d3"]["supports"], [["d1"]])
            self.assertEqual(by_id["d3"]["answers"], ["q2"])
            self.assertEqual(by_id["d3"]["supersedes"], [])
            self.assertEqual(by_id["d3"]["depends_on"], ["d1"])
            self.assertEqual(by_id["q2"]["rationale"], "Choose one later")
            self.assertEqual(by_id["q2"]["legacy"]["raw"], self.source_records()[1])
            audit = by_id["d3"]["legacy"]["relation_map"]
            self.assertEqual(audit["source_supersedes"], ["d2"])
            self.assertEqual(audit["mapped_answers"], ["q2"])
            self.assertEqual(audit["mapped_supersedes"], [])
            self.assertEqual(audit["source_depends_on"], [])
            self.assertEqual(audit["mapped_depends_on"], ["d1"])
            self.assertIn("depends_on", audit["overrides"])
            self.assertEqual(
                source.read_text().splitlines(),
                [json.dumps(record) for record in self.source_records()],
            )

    def test_cross_kind_supersession_requires_explicit_treatment(self):
        migrator = load_migrator()
        mapping = self.mapping()
        del mapping["d3"]["answers"]
        del mapping["d3"]["supersedes"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "old.jsonl"
            map_path = root / "map.json"
            output = root / "new.jsonl"
            write_jsonl(source, self.source_records())
            map_path.write_text(json.dumps(mapping))
            with self.assertRaises(migrator.MigrationError) as raised:
                migrator.migrate(source, map_path, output)
            self.assertIn("cross-kind supersession", str(raised.exception))
            self.assertFalse(output.exists())

    def test_cross_kind_supersession_can_be_explicitly_removed(self):
        migrator = load_migrator()
        records = self.source_records()[:2]
        records[1]["supersedes"] = ["d1"]
        mapping = self.mapping()
        mapping["d2"] = {
            "kind": "claim",
            "state": "accepted",
            "text": "Which validator?",
            "supersedes": [],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "old.jsonl"
            map_path = root / "map.json"
            output = root / "new.jsonl"
            write_jsonl(source, records)
            map_path.write_text(json.dumps({key: mapping[key] for key in ("d1", "d2")}))
            migrator.migrate(source, map_path, output)
            migrated = [json.loads(line) for line in output.read_text().splitlines()]
            by_id = {record["id"]: record for record in migrated}
            self.assertEqual(by_id["c2"]["supersedes"], [])
            self.assertEqual(by_id["c2"]["legacy"]["relation_map"]["source_supersedes"], ["d1"])

    def test_missing_mapping_is_rejected_before_output_creation(self):
        migrator = load_migrator()
        mapping = self.mapping()
        del mapping["d2"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "old.jsonl"
            map_path = root / "map.json"
            output = root / "new.jsonl"
            write_jsonl(source, self.source_records())
            map_path.write_text(json.dumps(mapping))
            with self.assertRaises(migrator.MigrationError) as raised:
                migrator.migrate(source, map_path, output)
            self.assertIn("missing mapping", str(raised.exception))
            self.assertFalse(output.exists())

    def test_unknown_relation_reference_is_rejected(self):
        migrator = load_migrator()
        records = self.source_records()
        records[1]["because"] = ["d404"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "old.jsonl"
            map_path = root / "map.json"
            output = root / "new.jsonl"
            write_jsonl(source, records)
            map_path.write_text(json.dumps(self.mapping()))
            with self.assertRaises(migrator.MigrationError) as raised:
                migrator.migrate(source, map_path, output)
            self.assertIn("unknown reference", str(raised.exception))
            self.assertFalse(output.exists())

    def test_malformed_input_and_existing_output_are_refused(self):
        migrator = load_migrator()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "old.jsonl"
            map_path = root / "map.json"
            output = root / "new.jsonl"
            source.write_text('{"id":"d1"}\nnot-json\n')
            map_path.write_text(json.dumps({"d1": self.mapping()["d1"]}))
            with self.assertRaises(migrator.MigrationError) as raised:
                migrator.migrate(source, map_path, output)
            self.assertIn("malformed input", str(raised.exception))

            write_jsonl(source, [self.source_records()[0]])
            output.write_text("keep me\n")
            with self.assertRaises(migrator.MigrationError) as raised:
                migrator.migrate(source, map_path, output)
            self.assertIn("already exists", str(raised.exception))
            self.assertEqual(output.read_text(), "keep me\n")

    def test_core_validation_happens_before_destination_is_created(self):
        migrator = load_migrator()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "old.jsonl"
            map_path = root / "map.json"
            output = root / "new.jsonl"
            write_jsonl(source, [self.source_records()[0]])
            map_path.write_text(json.dumps({"d1": self.mapping()["d1"]}))

            def reject(_records):
                raise ValueError("core rejected test output")

            with self.assertRaisesRegex(ValueError, "core rejected"):
                migrator.migrate(source, map_path, output, validator=reject)
            self.assertFalse(output.exists())


class DerivationTests(unittest.TestCase):
    def test_a_settled_record_becomes_an_adopted_decision(self):
        source = [
            {
                "id": "d1",
                "state": "settled",
                "question": "Ship it?",
                "answer": "Yes, on Friday.",
                "because": [],
            }
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d1"]["kind"], "decision")
        self.assertEqual(derived["d1"]["state"], "adopted")
        self.assertEqual(derived["d1"]["text"], "Ship it?")
        self.assertEqual(derived["d1"]["choice"], "Yes, on Friday.")

    def test_a_ruled_out_record_stays_adopted(self):
        # A ruled-out record commits to not doing something and still applies.
        # A revoked decision renders as unusable support.
        source = [
            {
                "id": "d1",
                "state": "ruled-out",
                "question": "Delete the key?",
                "answer": "No. Another team still sends it.",
                "because": [],
            }
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d1"]["kind"], "decision")
        self.assertEqual(derived["d1"]["state"], "adopted")
        self.assertEqual(derived["d1"]["choice"], "No. Another team still sends it.")

    def test_an_open_record_becomes_a_question(self):
        source = [
            {
                "id": "d1",
                "state": "open",
                "question": "Which validator?",
                "answer": "Undecided.",
                "because": [],
            }
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d1"]["kind"], "question")
        self.assertEqual(derived["d1"]["state"], "open")
        self.assertNotIn("choice", derived["d1"])

    def test_an_unknown_state_is_rejected_and_named(self):
        source = [{"id": "d1", "state": "parked", "question": "Q", "answer": "A", "because": []}]
        with self.assertRaises(docket_migrate.MigrationError) as caught:
            docket_migrate.derive_mapping(source)
        self.assertIn("parked", str(caught.exception))
        self.assertIn("d1", str(caught.exception))

    def test_a_settled_record_without_an_answer_is_rejected(self):
        source = [{"id": "d1", "state": "settled", "question": "Q", "answer": "", "because": []}]
        with self.assertRaises(docket_migrate.MigrationError) as caught:
            docket_migrate.derive_mapping(source)
        self.assertIn("d1", str(caught.exception))

    def test_the_derived_map_passes_read_mapping(self):
        source = [
            {"id": "d1", "state": "settled", "question": "Q1", "answer": "A1", "because": []},
            {"id": "d2", "state": "open", "question": "Q2", "answer": "A2", "because": ["d1"]},
        ]
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "map.json"
            path.write_text(json.dumps(docket_migrate.derive_mapping(source)))
            loaded = docket_migrate.read_mapping(path, {"d1", "d2"})
        self.assertEqual(set(loaded), {"d1", "d2"})

    def test_version_detection(self):
        self.assertEqual(docket_migrate.detect_version([{"id": "d1"}]), 1)
        self.assertEqual(docket_migrate.detect_version([{"schema": 1}]), 1)
        self.assertEqual(docket_migrate.detect_version([{"schema": 2}]), 2)
        self.assertEqual(docket_migrate.detect_version([{"schema": 3}]), 3)
        with self.assertRaises(docket_migrate.MigrationError):
            docket_migrate.detect_version([{"schema": 1}, {"schema": 2}])

    def test_a_settled_record_superseding_an_open_record_becomes_an_answer(self):
        source = [
            {
                "id": "d19",
                "state": "open",
                "question": "SSH reachability?",
                "answer": "",
                "because": [],
            },
            {
                "id": "d25",
                "state": "settled",
                "question": "SSH reachability for GCE instances (closes d19)",
                "answer": "Yes.",
                "because": [],
                "supersedes": ["d19"],
            },
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d25"]["supersedes"], [])
        self.assertEqual(derived["d25"]["answers"], ["d19"])
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, source)
            docket_migrate.migrate_in_place(path)
            from docket.ledger import project
            from docket.ledger import read as ledger_read

            entries = ledger_read(path)
            projected = {r["id"]: r for r in project(entries)}
        self.assertEqual(projected["q1"]["state"], "resolved")

    def test_an_open_record_superseding_an_open_record_keeps_supersedes(self):
        source = [
            {"id": "d6", "state": "open", "question": "Q6", "answer": "", "because": []},
            {
                "id": "d19",
                "state": "open",
                "question": "Q19",
                "answer": "",
                "because": [],
                "supersedes": ["d6"],
            },
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertNotIn("supersedes", derived["d19"])
        self.assertNotIn("answers", derived["d19"])

    def test_a_support_edge_into_a_question_is_dropped(self):
        source = [
            {
                "id": "d1",
                "state": "open",
                "question": "How do they authenticate?",
                "answer": "",
                "because": [],
            },
            {
                "id": "d6",
                "state": "settled",
                "question": "Ship the connector?",
                "answer": "Yes.",
                "because": [["d1"]],
            },
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d6"]["supports"], [])
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, source)
            docket_migrate.migrate_in_place(path)
            converted = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        by_id = {r["id"]: r for r in converted}
        self.assertEqual(by_id["d1"]["supports"], [])
        self.assertEqual(by_id["d1"]["migrated_from"], "d6")
        self.assertEqual(by_id["d1"]["legacy"]["relation_map"]["source_because"], [["d1"]])

    def test_a_justification_set_keeps_its_non_question_member(self):
        source = [
            {"id": "d1", "state": "open", "question": "Q1", "answer": "", "because": []},
            {"id": "d2", "state": "settled", "question": "Q2", "answer": "Yes.", "because": []},
            {
                "id": "d3",
                "state": "settled",
                "question": "Q3",
                "answer": "Yes.",
                "because": [["d1", "d2"]],
            },
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d3"]["supports"], [["d2"]])

    def test_both_rules_emit_a_note_naming_both_records(self):
        source = [
            {"id": "d1", "state": "open", "question": "Q1", "answer": "", "because": []},
            {
                "id": "d2",
                "state": "settled",
                "question": "Q2 (closes d1)",
                "answer": "Yes.",
                "because": [],
                "supersedes": ["d1"],
            },
        ]
        notes: list[str] = []
        docket_migrate.derive_mapping(source, notes=notes)
        self.assertEqual(notes, ["d2 supersedes d1, a question; recorded as an answers edge"])

        source = [
            {"id": "d1", "state": "open", "question": "Q1", "answer": "", "because": []},
            {
                "id": "d6",
                "state": "settled",
                "question": "Q6",
                "answer": "Yes.",
                "because": [["d1"]],
            },
        ]
        notes = []
        docket_migrate.derive_mapping(source, notes=notes)
        self.assertEqual(
            notes,
            [
                "d6 is justified by d1, a question; support edge dropped and "
                "kept in legacy.relation_map.source_because"
            ],
        )


def legacy_ledger() -> list[dict]:
    return [
        {
            "id": "d1",
            "ts": "2026-01-01T00:00:00+00:00",
            "state": "settled",
            "question": "Ship it?",
            "answer": "Yes.",
            "because": [],
            "supersedes": [],
            "cost_if_wrong": "",
            "session": "",
            "author": "",
            "branch": "",
        },
        {
            "id": "d2",
            "ts": "2026-01-02T00:00:00+00:00",
            "state": "ruled-out",
            "question": "Delete the key?",
            "answer": "No.",
            "because": ["d1"],
            "supersedes": [],
            "cost_if_wrong": "",
            "session": "",
            "author": "",
            "branch": "",
        },
    ]


class InPlaceTests(unittest.TestCase):
    def test_conversion_replaces_the_file_and_keeps_the_original(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, legacy_ledger())
            original = path.read_bytes()
            result = docket_migrate.migrate_in_place(path)
            self.assertEqual(result.count, 2)
            backup = Path(str(path) + ".schema1")
            self.assertEqual(backup.read_bytes(), original)
            converted = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            self.assertEqual([r["id"] for r in converted], ["d1", "d2"])
            self.assertTrue(all(r["schema"] == 3 for r in converted))

    def test_the_result_reads_back_through_the_ledger_reader(self):
        from docket.ledger import read as ledger_read

        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, legacy_ledger())
            docket_migrate.migrate_in_place(path)
            self.assertEqual(len(ledger_read(path)), 2)

    def test_an_existing_backup_stops_the_command(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, legacy_ledger())
            Path(str(path) + ".schema1").write_text("earlier\n")
            before = path.read_bytes()
            with self.assertRaises(docket_migrate.MigrationError):
                docket_migrate.migrate_in_place(path)
            self.assertEqual(path.read_bytes(), before)

    def test_a_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, legacy_ledger())
            before = path.read_bytes()
            result = docket_migrate.migrate_in_place(path, dry_run=True)
            self.assertEqual(result.count, 2)
            self.assertEqual(len(result.report), 2)
            self.assertIn("d1", result.report[0])
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(str(path) + ".schema1").exists())

    def test_a_failure_leaves_the_ledger_untouched(self):
        records = legacy_ledger()
        records[0]["state"] = "parked"
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, records)
            before = path.read_bytes()
            with self.assertRaises(docket_migrate.MigrationError):
                docket_migrate.migrate_in_place(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(str(path) + ".schema1").exists())
            self.assertFalse(Path(str(path) + ".migrating").exists())

    def test_an_explicit_map_overrides_the_derived_one(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            path = work / "ledger.jsonl"
            write_jsonl(path, legacy_ledger())
            override = docket_migrate.derive_mapping(legacy_ledger())
            override["d1"]["kind"] = "claim"
            override["d1"]["state"] = "accepted"
            override["d1"]["id"] = "c1"
            override["d1"].pop("choice")
            override["d2"]["supports"] = [["d1"]]
            map_path = work / "map.json"
            map_path.write_text(json.dumps(override))
            docket_migrate.migrate_in_place(path, mapping_path=map_path)
            converted = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            self.assertEqual(converted[0]["kind"], "claim")
            self.assertEqual(converted[0]["id"], "c1")


def schema_two_ledger() -> list[dict]:
    """Seven schema-2 lines: every kind, a correction, a review, and a prose mention chain."""

    def make(kind, ident, text, **kwargs):
        record = make_record(kind, text, author="t", ts="2026-10-01T00:00:00+00:00", **kwargs)
        return {**record, "id": ident, "schema": 2}

    chosen = make("decision", "d2", "Cache in Redis", choice="Redis", supports=[["c1"]])
    chosen["legacy"] = {"source_id": "d1", "relation_map": {"mapped_answers": ["q99"]}}
    retiring = make("decision", "d4", "Cache for sixty seconds", choice="Redis, 60s")
    retiring.update(
        answers=["q3"],
        supersedes=["d2"],
        supports=[["c1"]],
        rationale="Replaces d2 after q3; c1 still holds",
    )
    fix = {
        "schema": 2,
        "kind": "correction",
        "id": "d4.1",
        "corrects": "d4",
        "fields": {"rationale": "Replaces d2 after q3."},
        "reason": "",
        "ts": "2026-10-01T00:00:01+00:00",
        "author": "t",
        "session": "",
        "branch": "",
    }
    review = {
        "schema": 2,
        "kind": "review",
        "id": "d4.r1",
        "reviews": "d4",
        "grounds": {"c1": "c1"},
        "note": "",
        "ts": "2026-10-01T00:00:02+00:00",
        "author": "t",
        "session": "",
        "branch": "",
    }
    return [
        make("claim", "c1", "Reads are cached", state="accepted"),
        chosen,
        make("question", "q3", "Which TTL?"),
        retiring,
        fix,
        review,
        make("claim", "c5", "d4 settles the TTL, d2 is retired", supports=[["c1"]]),
    ]


class MigrationEdgeTests(unittest.TestCase):
    def test_a_ledger_that_cannot_be_renumbered_is_refused_untouched(self):
        # A hand-resolved merge can leave one id twice; renumbering it would
        # point every later citation of that id at one of the two by chance.
        first = {**make_record("claim", "One", author="t", record_id="c1"), "schema": 2}
        twin = {**make_record("claim", "Two", author="t", record_id="c1"), "schema": 2}
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, [first, twin])
            before = path.read_bytes()
            with self.assertRaisesRegex(docket_migrate.MigrationError, "docket check"):
                docket_migrate.migrate_in_place(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(str(path) + ".schema2").exists())

    def test_an_empty_ledger_has_nothing_to_migrate(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            path.write_text("")
            result = docket_migrate.migrate_in_place(path)
            self.assertEqual(result.count, 0)
            self.assertEqual(path.read_text(), "")
            self.assertFalse(Path(str(path) + ".schema2").exists())

    def test_two_thousand_records_migrate_in_linear_time(self):
        rows: list[dict] = []
        for n in range(1, 2001):
            kind = ("claim", "decision", "question")[n % 3]
            fields: dict = {"choice": "Chosen"} if kind == "decision" else {}
            if kind == "decision" and n > 3:
                # n % 3 == 1 here, so the line before is a claim.
                fields["supports"] = [[rows[-1]["id"]]]
            cites = rows[-1]["id"] if rows else "nothing"
            made = make_record(
                kind, f"Record {n} follows {cites}", author="t", record_id=f"{kind[0]}{n}", **fields
            )
            rows.append({**made, "schema": 2})
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, rows)
            start = time.monotonic()
            result = docket_migrate.migrate_in_place(path, dry_run=True)
            # Generous: a quadratic pass over 2000 lines takes far longer.
            self.assertLess(time.monotonic() - start, 5.0)
            self.assertEqual(result.count, 2000)
            self.assertEqual(result.per_kind, {"claim": 666, "decision": 667, "question": 667})


class SchemaThreeTests(unittest.TestCase):
    def test_the_latest_schema_is_the_ledgers(self):
        self.assertEqual(docket_migrate.SCHEMA_LATEST, SCHEMA)

    def test_schema_two_becomes_three_with_per_kind_ids(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, schema_two_ledger())
            original = path.read_bytes()
            result = docket_migrate.migrate_in_place(path)
            self.assertEqual(Path(str(path) + ".schema2").read_bytes(), original)
            self.assertFalse(Path(str(path) + ".schema1").exists())
            lines = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(
                [line["id"] for line in lines],
                ["c1", "d1", "q1", "d2", "d2.1", "d2.r1", "c2"],
            )
            self.assertTrue(all(line["schema"] == 3 for line in lines))
            self.assertEqual(
                [line.get("migrated_from") for line in lines],
                ["c1", "d2", "q3", "d4", None, None, "c5"],
            )
            by_id = {line["id"]: line for line in lines}
            self.assertEqual(by_id["d2"]["supersedes"], ["d1"])
            self.assertEqual(by_id["d2"]["answers"], ["q1"])
            self.assertEqual(by_id["d2.1"]["corrects"], "d2")
            self.assertEqual(by_id["d2.r1"]["reviews"], "d2")
            self.assertEqual(by_id["d1"]["legacy"], schema_two_ledger()[1]["legacy"])
            # d4 -> d2 and d2 -> d1 in one line: a chained rewrite would give d1 twice.
            self.assertEqual(by_id["c2"]["text"], "d2 settles the TTL, d1 is retired")
            self.assertEqual(by_id["d2"]["rationale"], "Replaces d1 after q1; c1 still holds")
            self.assertEqual(by_id["d2.1"]["fields"], {"rationale": "Replaces d1 after q1."})
            self.assertEqual(
                result.mapping, {"c1": "c1", "d2": "d1", "q3": "q1", "d4": "d2", "c5": "c2"}
            )
            self.assertEqual(result.per_kind, {"claim": 2, "decision": 2, "question": 1})
            self.assertEqual(
                sorted(change.field for change in result.prose_changes),
                ["rationale", "rationale", "text"],
            )
            self.assertTrue(all(change.after is not None for change in result.prose_changes))
            self.assertEqual(result.count, 7)
            self.assertEqual(result.backup, str(path) + ".schema2")
            self.assertEqual(len(ledger_read(path)), 7)

    def test_schema_one_reaches_three_in_one_run(self):
        third = dict(legacy_ledger()[1], id="d3", ts="2026-01-03T00:00:00+00:00")
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, [*legacy_ledger(), third])
            original = path.read_bytes()
            result = docket_migrate.migrate_in_place(path)
            self.assertEqual(Path(str(path) + ".schema1").read_bytes(), original)
            self.assertFalse(Path(str(path) + ".schema2").exists())
            lines = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([line["id"] for line in lines], ["d1", "d2", "d3"])
            self.assertEqual([line["migrated_from"] for line in lines], ["d1", "d2", "d3"])
            self.assertEqual([line["legacy"]["source_id"] for line in lines], ["d1", "d2", "d3"])
            self.assertTrue(all(line["schema"] == 3 for line in lines))
            self.assertEqual(result.report[0], "d1 -> d1 decision/adopted")

    def test_a_schema_one_question_keeps_its_schema_two_id_as_migrated_from(self):
        source = legacy_ledger()
        source[1]["state"] = "open"
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, source)
            result = docket_migrate.migrate_in_place(path)
            lines = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([line["id"] for line in lines], ["d1", "q1"])
            self.assertEqual(lines[1]["migrated_from"], "q2")
            self.assertEqual(lines[1]["legacy"]["source_id"], "d2")
            self.assertEqual(result.report, ["d1 -> d1 decision/adopted", "d2 -> q1 question/open"])

    def test_a_map_applies_only_to_schema_one(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, schema_two_ledger())
            before = path.read_bytes()
            with self.assertRaisesRegex(docket_migrate.MigrationError, "applies only to schema 1"):
                docket_migrate.migrate_in_place(path, mapping_path=Path(work) / "map.json")
            self.assertEqual(path.read_bytes(), before)

    def test_a_schema_three_ledger_is_left_alone(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, [make_record("claim", "one", author="t", record_id="c1")])
            before = path.read_bytes()
            result = docket_migrate.migrate_in_place(path)
            self.assertEqual(result.count, 0)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(str(path) + ".schema3").exists())

    def test_an_existing_backup_of_the_starting_schema_stops_the_run(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, schema_two_ledger())
            Path(str(path) + ".schema2").write_text("earlier\n")
            before = path.read_bytes()
            with self.assertRaisesRegex(docket_migrate.MigrationError, "already exists"):
                docket_migrate.migrate_in_place(path)
            self.assertEqual(path.read_bytes(), before)

    def test_a_dry_run_reports_every_line_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, schema_two_ledger())
            before = path.read_bytes()
            result = docket_migrate.migrate_in_place(path, dry_run=True)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(
                result.report,
                [
                    "c1 -> c1 claim/accepted",
                    "d2 -> d1 decision/adopted",
                    "q3 -> q1 question/open",
                    "d4 -> d2 decision/adopted",
                    "d4.1 -> d2.1 correction",
                    "d4.r1 -> d2.r1 review",
                    "c5 -> c2 claim/unassessed",
                ],
            )
            self.assertFalse(Path(str(path) + ".schema2").exists())

    def test_a_failing_step_leaves_the_ledger_untouched(self):
        records = schema_two_ledger()
        records[3]["supersedes"] = ["q3"]
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, records)
            before = path.read_bytes()
            with self.assertRaises(LedgerError):
                docket_migrate.migrate_in_place(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(str(path) + ".migrating").exists())


class FeaturesMoveTests(unittest.TestCase):
    TS = "2026-01-01T00:00:00+00:00"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / ".docket"
        (self.dir / "archive").mkdir(parents=True)
        self.path = self.dir / "ledger.jsonl"
        self.store = self.dir / "features.jsonl"
        self.archive = self.dir / "archive" / "features-abc123.jsonl"
        # Old ids c1 d2 c3 c4 become c1 d1 c2 c3. c3 cites d2 in its headline.
        self.c1 = self.rec("claim", "c1", "First premise", state="accepted")
        self.d2 = self.rec(
            "decision",
            "d2",
            "Cache layer sits behind reads",
            state="adopted",
            choice="Cache",
            alternatives=["No cache"],
            rationale="Reads dominate",
            supports=[["c1"]],
        )
        self.c3 = self.rec("claim", "c3", "Contradicts d2 outright", state="accepted")
        self.c4 = self.rec("claim", "c4", "Fourth premise", state="accepted")
        write_jsonl(self.path, [self.c1, self.d2, self.c3, self.c4])

    def rec(self, kind, ident, text, **fields):
        made = ledger.make_record(
            kind, text, author="t", session="s", ts=self.TS, record_id=ident, **fields
        )
        return dict(made, schema=2)

    def old_key(self, entry):
        parts = (entry["kind"], entry["ts"], entry["author"], entry["session"], entry["text"])
        return hashlib.sha1("\0".join(parts).encode("utf-8")).hexdigest()[:12]

    def event(self, ident, slug, **fields):
        made = features.make_event("start", slug, text=slug, paths=["src/**"], ts=self.TS, **fields)
        return dict(made, id=ident, schema=1)

    def ledger_schema(self):
        return json.loads(self.path.read_text().splitlines()[0])["schema"]

    def test_features_and_archive_follow_the_ledger(self):
        keys = {
            "c4": self.old_key(self.c4),
            "c3": self.old_key(self.c3),
            "d2": self.old_key(self.d2),
        }
        write_jsonl(
            self.store,
            [self.event("f2", "live", include=["c4", "c3"], exclude=["d2"], keys=keys)],
        )
        write_jsonl(
            self.archive,
            [self.event("f1", "old", include=["c4"], keys={"c4": self.old_key(self.c4)})],
        )
        result = docket_migrate.migrate_in_place(self.path)
        self.assertEqual(result.features_events, 2)

        by_id = {e["id"]: e for e in ledger.project(ledger.read(self.path))}
        [live] = features.read(self.store)
        self.assertEqual(live["schema"], 2)
        self.assertEqual(live["include"], ["c3", "c2"])
        self.assertEqual(live["exclude"], ["d1"])
        self.assertEqual(live["keys"], {i: ledger.record_key(by_id[i]) for i in ("c3", "c2", "d1")})
        # c4 has no token in its headline, so its key is the one stored before.
        self.assertEqual(live["keys"]["c3"], self.old_key(self.c4))
        # c3 mentions d2 in its headline. The rewrite to d1 must not move the key.
        self.assertNotEqual(live["keys"]["c2"], self.old_key(self.c3))
        [archived] = features.read(self.archive)
        self.assertEqual(archived["include"], ["c3"])
        self.assertEqual(archived["keys"], {"c3": self.old_key(self.c4)})

    def test_a_crash_before_the_ledger_swap_is_repaired_by_a_rerun(self):
        write_jsonl(
            self.store,
            [self.event("f1", "live", include=["c4"], keys={"c4": self.old_key(self.c4)})],
        )
        original = self.path.read_bytes()
        real = os.replace
        ledger_path = self.path

        def fail(source, target):
            if Path(target) == ledger_path:
                raise OSError("disk full")
            return real(source, target)

        with mock.patch.object(os, "replace", fail), self.assertRaises(OSError):
            docket_migrate.migrate_in_place(self.path)
        # Never a moment with no ledger: still the schema-2 file, backup beside it.
        self.assertEqual(self.path.read_bytes(), original)
        backup = Path(str(self.path) + ".schema2")
        self.assertEqual(backup.read_bytes(), original)
        [after_crash] = features.read(self.store)
        self.assertEqual(after_crash["include"], ["c3"])

        docket_migrate.migrate_in_place(self.path)
        self.assertEqual(self.ledger_schema(), 3)
        self.assertEqual(backup.read_bytes(), original)
        # c4 -> c3 once. A second mapping would have sent it on to c2.
        self.assertEqual(features.read(self.store), [after_crash])
        self.assertFalse(Path(str(self.path) + ".migrating").exists())

    def test_a_backup_that_differs_from_the_ledger_stops_the_command(self):
        Path(str(self.path) + ".schema2").write_text("earlier\n")
        before = self.path.read_bytes()
        with self.assertRaises(docket_migrate.MigrationError):
            docket_migrate.migrate_in_place(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_a_stale_temp_from_a_crashed_run_is_overwritten(self):
        write_jsonl(self.store, [self.event("f1", "live", include=["c4"])])
        Path(str(self.path) + ".migrating").write_text("junk\n")
        Path(str(self.store) + ".migrating").write_text("junk\n")
        docket_migrate.migrate_in_place(self.path)
        self.assertEqual(features.read(self.store)[0]["include"], ["c3"])
        self.assertEqual(self.ledger_schema(), 3)

    def test_a_features_file_already_at_schema_two_is_left_alone(self):
        write_jsonl(self.store, [dict(self.event("f1", "live", include=["c4"]), schema=2)])
        before = self.store.read_bytes()
        result = docket_migrate.migrate_in_place(self.path)
        self.assertEqual(result.features_events, 0)
        self.assertEqual(self.store.read_bytes(), before)

    def test_a_dry_run_counts_features_events_and_writes_nothing(self):
        write_jsonl(self.store, [self.event("f1", "live", include=["c4"])])
        before = self.store.read_bytes()
        result = docket_migrate.migrate_in_place(self.path, dry_run=True)
        self.assertEqual(result.features_events, 1)
        self.assertEqual(self.store.read_bytes(), before)
        self.assertEqual(self.ledger_schema(), 2)

    def test_a_ledger_with_no_features_files_migrates(self):
        result = docket_migrate.migrate_in_place(self.path)
        self.assertEqual(result.features_events, 0)
        self.assertFalse(self.store.exists())

    def test_a_migrated_ledger_remaps_features_still_at_schema_one(self):
        docket_migrate.migrate_in_place(self.path)
        ledger_bytes = self.path.read_bytes()
        write_jsonl(
            self.store,
            [self.event("f1", "late", include=["c4"], keys={"c4": self.old_key(self.c4)})],
        )
        result = docket_migrate.migrate_in_place(self.path)
        self.assertEqual(result.features_events, 1)
        self.assertEqual(features.read(self.store)[0]["include"], ["c3"])
        self.assertEqual(self.path.read_bytes(), ledger_bytes)

    def test_an_old_id_held_by_two_records_is_not_mapped(self):
        records = [
            {"id": "c2", "migrated_from": "c3"},
            {"id": "c3", "migrated_from": "c3"},
            {"id": "d1", "migrated_from": "d2"},
            {"id": "c1"},
        ]
        self.assertEqual(docket_migrate._migrated_map(records), {"d2": "d1"})


def s2(kind: str, ident: str, text: str, **fields) -> dict:
    if kind == "decision":
        fields.setdefault("choice", "chosen")
    record = make_record(
        kind, text, record_id=ident, ts="2026-09-12T00:00:00+00:00", author="t", **fields
    )
    return {**record, "schema": 2}


def schema2_ledger() -> list[dict]:
    # One global counter with gaps. Per kind: c1->c1, d2->d1, c3->c2, d4->d2, q5->q1.
    return [
        s2("claim", "c1", "First claim"),
        s2("decision", "d2", "Use the first claim", supports=[["c1"]]),
        s2("claim", "c3", "Second claim"),
        s2("decision", "d4", "Follows d2 and c3", supports=[["c3"]]),
        s2("question", "q5", "What next"),
    ]


def git(work: Path, *args: str) -> None:
    base = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*base, *args], cwd=work, check=True, capture_output=True)


class ReadSourceTests(unittest.TestCase):
    def test_typed_schema_2_lines_skip_the_old_id_check(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, schema2_ledger())
            records = docket_migrate.read_source(path)
            self.assertEqual([r["id"] for r in records], ["c1", "d2", "c3", "d4", "q5"])
            self.assertEqual(docket_migrate.detect_version(records), 2)


class RewriteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name)
        self.path = self.work / "ledger.jsonl"
        write_jsonl(self.path, schema2_ledger())
        self.doc = self.work / "notes.md"
        self.doc.write_text("d4 then d2, see c3 and q5. Keep c9 and d2.1.\n")
        git(self.work, "init", "-q")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "fixture")

    def test_rewrite_text_is_one_lookup_per_token(self):
        mapping = {"d4": "d2", "d2": "d1"}
        self.assertEqual(
            docket_migrate.rewrite_text("d4 then d2; d4x, d2.1, d20", mapping),
            ("d2 then d1; d4x, d1.1, d20", 3),
        )

    def test_an_identity_mapping_counts_nothing(self):
        self.assertEqual(docket_migrate.rewrite_text("c1 and c1", {"c1": "c1"}), ("c1 and c1", 0))

    def test_rewrite_rewrites_named_files_in_the_migration_run(self):
        other = self.work / "plain.md"
        other.write_text("no ids here\n")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "plain")
        result = docket_migrate.migrate_in_place(self.path, rewrite=[self.doc, other])
        self.assertEqual(self.doc.read_text(), "d2 then d1, see c2 and q1. Keep c9 and d1.1.\n")
        self.assertEqual(other.read_text(), "no ids here\n")
        self.assertEqual(result.rewritten, [str(self.doc)])
        self.assertEqual(result.rewrite_counts, {str(self.doc): 5})
        self.assertTrue(Path(str(self.path) + ".schema2").exists())

    def test_dry_run_plans_the_rewrite_and_writes_nothing(self):
        before = (self.path.read_bytes(), self.doc.read_bytes())
        result = docket_migrate.migrate_in_place(self.path, dry_run=True, rewrite=[self.doc])
        self.assertEqual(result.rewritten, [str(self.doc)])
        self.assertEqual(result.rewrite_counts, {str(self.doc): 5})
        self.assertEqual((self.path.read_bytes(), self.doc.read_bytes()), before)

    def test_rewrite_is_refused_on_a_ledger_already_at_schema_3(self):
        docket_migrate.migrate_in_place(self.path)
        migrated = self.path.read_bytes()
        with self.assertRaisesRegex(docket_migrate.MigrationError, "already at schema 3"):
            docket_migrate.migrate_in_place(self.path, rewrite=[self.doc])
        with self.assertRaisesRegex(docket_migrate.MigrationError, "already at schema 3"):
            docket_migrate.migrate_in_place(self.path, dry_run=True, rewrite=[self.doc])
        self.assertEqual(self.path.read_bytes(), migrated)
        self.assertEqual(self.doc.read_text(), "d4 then d2, see c3 and q5. Keep c9 and d2.1.\n")

    def test_an_untracked_file_is_refused_before_anything_is_written(self):
        fresh = self.work / "fresh.md"
        fresh.write_text("d4\n")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(docket_migrate.MigrationError, "not tracked"):
            docket_migrate.migrate_in_place(self.path, rewrite=[self.doc, fresh])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(Path(str(self.path) + ".schema2").exists())
        self.assertEqual(fresh.read_text(), "d4\n")

    def test_a_file_with_uncommitted_changes_is_refused(self):
        self.doc.write_text("d4 edited\n")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(docket_migrate.MigrationError, "uncommitted"):
            docket_migrate.migrate_in_place(self.path, rewrite=[self.doc])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.doc.read_text(), "d4 edited\n")

    def test_a_file_outside_a_git_repository_is_refused(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            loose = Path(elsewhere) / "loose.md"
            loose.write_text("d4\n")
            with self.assertRaisesRegex(docket_migrate.MigrationError, "not tracked"):
                docket_migrate.migrate_in_place(self.path, rewrite=[loose])

    def test_a_missing_directory_or_ledger_target_is_refused(self):
        before = self.path.read_bytes()
        for bad in (self.work / "missing.md", self.work, self.path):
            with self.assertRaises(docket_migrate.MigrationError, msg=str(bad)):
                docket_migrate.migrate_in_place(self.path, rewrite=[self.doc, bad])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(Path(str(self.path) + ".schema2").exists())

    def test_a_schema_1_ledger_rewrites_files_through_schema_1_ids(self):
        # d3 is an open question: schema 1 d3 becomes schema 2 q3, then q1.
        legacy = legacy_ledger() + [dict(legacy_ledger()[0], id="d3", state="open")]
        write_jsonl(self.path, legacy)
        self.doc.write_text("see d3 and d2, not q3\n")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "legacy")
        result = docket_migrate.migrate_in_place(self.path, rewrite=[self.doc])
        self.assertEqual(self.doc.read_text(), "see q1 and d2, not q3\n")
        self.assertEqual(result.rewrite_counts, {str(self.doc): 1})

    def test_naming_a_file_twice_is_refused(self):
        with self.assertRaisesRegex(docket_migrate.MigrationError, "twice"):
            docket_migrate.migrate_in_place(self.path, rewrite=[self.doc, self.doc])

    def test_map_is_refused_on_a_schema_2_ledger(self):
        mapping = self.work / "map.json"
        mapping.write_text("{}")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(docket_migrate.MigrationError, "schema 1"):
            docket_migrate.migrate_in_place(self.path, mapping_path=mapping)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
