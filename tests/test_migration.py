"""Tests for the explicit schema-1 to schema-2 migration tool."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import docket_migrate


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "migrate_ledger.py"


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
            self.assertEqual(source.read_text().splitlines(), [
                json.dumps(record) for record in self.source_records()
            ])

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

    def test_the_script_shim_runs_the_library(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            source = work / "old.jsonl"
            write_jsonl(source, self.source_records())
            mapping = work / "map.json"
            mapping.write_text(json.dumps(self.mapping()))
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source),
                 "--map", str(mapping), "--output", str(work / "new.jsonl")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((work / "new.jsonl").exists())


class DerivationTests(unittest.TestCase):
    def test_a_settled_record_becomes_an_adopted_decision(self):
        source = [{"id": "d1", "state": "settled", "question": "Ship it?",
                   "answer": "Yes, on Friday.", "because": []}]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d1"]["kind"], "decision")
        self.assertEqual(derived["d1"]["state"], "adopted")
        self.assertEqual(derived["d1"]["text"], "Ship it?")
        self.assertEqual(derived["d1"]["choice"], "Yes, on Friday.")

    def test_a_ruled_out_record_stays_adopted(self):
        # A ruled-out record commits to not doing something and still applies.
        # A revoked decision renders as unusable support.
        source = [{"id": "d1", "state": "ruled-out", "question": "Delete the key?",
                   "answer": "No. Another team still sends it.", "because": []}]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d1"]["kind"], "decision")
        self.assertEqual(derived["d1"]["state"], "adopted")
        self.assertEqual(derived["d1"]["choice"], "No. Another team still sends it.")

    def test_an_open_record_becomes_a_question(self):
        source = [{"id": "d1", "state": "open", "question": "Which validator?",
                   "answer": "Undecided.", "because": []}]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d1"]["kind"], "question")
        self.assertEqual(derived["d1"]["state"], "open")
        self.assertNotIn("choice", derived["d1"])

    def test_an_unknown_state_is_rejected_and_named(self):
        source = [{"id": "d1", "state": "parked", "question": "Q", "answer": "A",
                   "because": []}]
        with self.assertRaises(docket_migrate.MigrationError) as caught:
            docket_migrate.derive_mapping(source)
        self.assertIn("parked", str(caught.exception))
        self.assertIn("d1", str(caught.exception))

    def test_a_settled_record_without_an_answer_is_rejected(self):
        source = [{"id": "d1", "state": "settled", "question": "Q", "answer": "",
                   "because": []}]
        with self.assertRaises(docket_migrate.MigrationError) as caught:
            docket_migrate.derive_mapping(source)
        self.assertIn("d1", str(caught.exception))

    def test_the_derived_map_passes_read_mapping(self):
        source = [{"id": "d1", "state": "settled", "question": "Q1", "answer": "A1",
                   "because": []},
                  {"id": "d2", "state": "open", "question": "Q2", "answer": "A2",
                   "because": ["d1"]}]
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "map.json"
            path.write_text(json.dumps(docket_migrate.derive_mapping(source)))
            loaded = docket_migrate.read_mapping(path, {"d1", "d2"})
        self.assertEqual(set(loaded), {"d1", "d2"})

    def test_version_detection(self):
        self.assertEqual(docket_migrate.detect_version([{"id": "d1"}]), 1)
        self.assertEqual(docket_migrate.detect_version([{"schema": 1}]), 1)
        self.assertEqual(docket_migrate.detect_version([{"schema": 2}]), 2)
        with self.assertRaises(docket_migrate.MigrationError):
            docket_migrate.detect_version([{"schema": 1}, {"schema": 2}])

    def test_a_settled_record_superseding_an_open_record_becomes_an_answer(self):
        source = [
            {"id": "d19", "state": "open", "question": "SSH reachability?",
             "answer": "", "because": []},
            {"id": "d25", "state": "settled",
             "question": "SSH reachability for GCE instances (closes d19)",
             "answer": "Yes.", "because": [], "supersedes": ["d19"]},
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d25"]["supersedes"], [])
        self.assertEqual(derived["d25"]["answers"], ["d19"])
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, source)
            docket_migrate.migrate_in_place(path)
            from lib.docket_ledger import read as ledger_read, project
            entries = ledger_read(path)
            projected = {r["id"]: r for r in project(entries)}
        self.assertEqual(projected["q19"]["state"], "resolved")

    def test_an_open_record_superseding_an_open_record_keeps_supersedes(self):
        source = [
            {"id": "d6", "state": "open", "question": "Q6", "answer": "", "because": []},
            {"id": "d19", "state": "open", "question": "Q19", "answer": "",
             "because": [], "supersedes": ["d6"]},
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertNotIn("supersedes", derived["d19"])
        self.assertNotIn("answers", derived["d19"])

    def test_a_support_edge_into_a_question_is_dropped(self):
        source = [
            {"id": "d1", "state": "open", "question": "How do they authenticate?",
             "answer": "", "because": []},
            {"id": "d6", "state": "settled", "question": "Ship the connector?",
             "answer": "Yes.", "because": [["d1"]]},
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d6"]["supports"], [])
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, source)
            docket_migrate.migrate_in_place(path)
            converted = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        by_id = {r["id"]: r for r in converted}
        self.assertEqual(by_id["d6"]["supports"], [])
        self.assertEqual(by_id["d6"]["legacy"]["relation_map"]["source_because"], [["d1"]])

    def test_a_justification_set_keeps_its_non_question_member(self):
        source = [
            {"id": "d1", "state": "open", "question": "Q1", "answer": "", "because": []},
            {"id": "d2", "state": "settled", "question": "Q2", "answer": "Yes.",
             "because": []},
            {"id": "d3", "state": "settled", "question": "Q3", "answer": "Yes.",
             "because": [["d1", "d2"]]},
        ]
        derived = docket_migrate.derive_mapping(source)
        self.assertEqual(derived["d3"]["supports"], [["d2"]])

    def test_both_rules_emit_a_note_naming_both_records(self):
        source = [
            {"id": "d1", "state": "open", "question": "Q1", "answer": "", "because": []},
            {"id": "d2", "state": "settled", "question": "Q2 (closes d1)", "answer": "Yes.",
             "because": [], "supersedes": ["d1"]},
        ]
        notes: list[str] = []
        docket_migrate.derive_mapping(source, notes=notes)
        self.assertEqual(notes, ["d2 supersedes d1, a question; recorded as an answers edge"])

        source = [
            {"id": "d1", "state": "open", "question": "Q1", "answer": "", "because": []},
            {"id": "d6", "state": "settled", "question": "Q6", "answer": "Yes.",
             "because": [["d1"]]},
        ]
        notes = []
        docket_migrate.derive_mapping(source, notes=notes)
        self.assertEqual(
            notes,
            ["d6 is justified by d1, a question; support edge dropped and "
             "kept in legacy.relation_map.source_because"],
        )


class InPlaceTests(unittest.TestCase):
    def legacy(self) -> list[dict]:
        return [
            {"id": "d1", "ts": "2026-01-01T00:00:00+00:00", "state": "settled",
             "question": "Ship it?", "answer": "Yes.", "because": [],
             "supersedes": [], "cost_if_wrong": "", "session": "", "author": "",
             "branch": ""},
            {"id": "d2", "ts": "2026-01-02T00:00:00+00:00", "state": "ruled-out",
             "question": "Delete the key?", "answer": "No.", "because": ["d1"],
             "supersedes": [], "cost_if_wrong": "", "session": "", "author": "",
             "branch": ""},
        ]

    def test_conversion_replaces_the_file_and_keeps_the_original(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, self.legacy())
            original = path.read_bytes()
            count, _, _ = docket_migrate.migrate_in_place(path)
            self.assertEqual(count, 2)
            backup = Path(str(path) + ".schema1")
            self.assertEqual(backup.read_bytes(), original)
            converted = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            self.assertEqual([r["id"] for r in converted], ["d1", "d2"])
            self.assertTrue(all(r["schema"] == 2 for r in converted))

    def test_the_result_reads_back_through_the_ledger_reader(self):
        from lib.docket_ledger import read as ledger_read
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, self.legacy())
            docket_migrate.migrate_in_place(path)
            self.assertEqual(len(ledger_read(path)), 2)

    def test_an_existing_backup_stops_the_command(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, self.legacy())
            Path(str(path) + ".schema1").write_text("earlier\n")
            before = path.read_bytes()
            with self.assertRaises(docket_migrate.MigrationError):
                docket_migrate.migrate_in_place(path)
            self.assertEqual(path.read_bytes(), before)

    def test_a_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "ledger.jsonl"
            write_jsonl(path, self.legacy())
            before = path.read_bytes()
            count, report, _ = docket_migrate.migrate_in_place(path, dry_run=True)
            self.assertEqual(count, 2)
            self.assertEqual(len(report), 2)
            self.assertIn("d1", report[0])
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(str(path) + ".schema1").exists())

    def test_a_failure_leaves_the_ledger_untouched(self):
        records = self.legacy()
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
            write_jsonl(path, self.legacy())
            override = docket_migrate.derive_mapping(self.legacy())
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


if __name__ == "__main__":
    unittest.main()
