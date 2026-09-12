"""Tests for the docket migrate subcommand."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DOCKET = ROOT / "bin" / "docket"


LEGACY = [
    {"id": "d1", "ts": "2026-01-01T00:00:00+00:00", "state": "settled",
     "question": "Ship it?", "answer": "Yes.", "because": [], "supersedes": [],
     "cost_if_wrong": "", "session": "", "author": "", "branch": ""},
    {"id": "d2", "ts": "2026-01-02T00:00:00+00:00", "state": "open",
     "question": "Which validator?", "answer": "Undecided.", "because": [],
     "supersedes": [], "cost_if_wrong": "", "session": "", "author": "",
     "branch": ""},
]


def project(work: Path, records: list[dict]) -> Path:
    """A git repository holding a project-local ledger."""
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    ledger = work / ".docket" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("".join(json.dumps(r) + "\n" for r in records))
    return ledger


def run(work: Path, *argv: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, DOCKET_HOME=str(work / "global"))
    return subprocess.run([sys.executable, str(DOCKET), *argv], cwd=work,
                          capture_output=True, text=True, env=env)


class MigrateCliTests(unittest.TestCase):
    def test_migration_converts_the_project_ledger(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, LEGACY)
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
            self.assertEqual([r["id"] for r in records], ["d1", "q2"])
            self.assertTrue(Path(str(ledger) + ".schema1").exists())

    def test_a_converted_ledger_lists(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            project(work, LEGACY)
            self.assertEqual(run(work, "migrate").returncode, 0)
            result = run(work, "list")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("d1", result.stdout)

    def test_a_schema_two_ledger_exits_clean_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, LEGACY)
            run(work, "migrate")
            after = ledger.read_bytes()
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already schema 2", result.stdout)
            self.assertEqual(ledger.read_bytes(), after)

    def test_a_dry_run_reports_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, LEGACY)
            before = ledger.read_bytes()
            result = run(work, "migrate", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("d1 -> d1 decision/adopted", result.stdout)
            self.assertIn("d2 -> q2 question/open", result.stdout)
            self.assertEqual(ledger.read_bytes(), before)
            self.assertFalse(Path(str(ledger) + ".schema1").exists())

    def test_emit_map_then_map_matches_the_derived_run(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, LEGACY)
            derived_source = ledger.read_bytes()
            self.assertEqual(run(work, "migrate").returncode, 0)
            derived_result = ledger.read_bytes()

            ledger.write_bytes(derived_source)
            Path(str(ledger) + ".schema1").unlink()
            emitted = work / "map.json"
            result = run(work, "migrate", "--emit-map", str(emitted))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(set(json.loads(emitted.read_text())), {"d1", "d2"})
            self.assertEqual(ledger.read_bytes(), derived_source)

            self.assertEqual(run(work, "migrate", "--map", str(emitted)).returncode, 0)
            self.assertEqual(ledger.read_bytes(), derived_result)

    def test_an_unknown_state_fails_and_names_the_record(self):
        records = [dict(LEGACY[0], state="parked")]
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, records)
            before = ledger.read_bytes()
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 2)
            self.assertIn("parked", result.stderr)
            self.assertIn("d1", result.stderr)
            self.assertIn("--emit-map", result.stderr)
            self.assertEqual(ledger.read_bytes(), before)

    def test_a_support_edge_into_a_question_converts_with_a_warning(self):
        # Rule B: a because target that derives to a question has no schema-2
        # relation, so the edge drops and the migration proceeds.
        records = [
            dict(LEGACY[1], id="d1", because=[]),
            dict(LEGACY[0], id="d2", because=["d1"]),
        ]
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, records)
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("d2 is justified by d1, a question", result.stderr)

    def test_a_ledger_needing_both_rules_converts_with_both_warnings(self):
        records = [
            dict(LEGACY[1], id="d1", because=[]),
            dict(LEGACY[0], id="d2", because=["d1"]),
            dict(LEGACY[1], id="d3", because=[]),
            dict(LEGACY[0], id="d4", because=[], supersedes=["d3"]),
        ]
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, records)
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("d2 is justified by d1, a question", result.stderr)
            self.assertIn("d4 supersedes d3, a question", result.stderr)

    def test_map_and_emit_map_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            project(work, LEGACY)
            result = run(work, "migrate", "--map", "a.json", "--emit-map", "b.json")
            self.assertNotEqual(result.returncode, 0)

    def test_the_validator_message_names_the_command(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            project(work, LEGACY)
            result = run(work, "list")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("docket migrate", result.stderr)


if __name__ == "__main__":
    unittest.main()
