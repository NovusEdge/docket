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


if __name__ == "__main__":
    unittest.main()
