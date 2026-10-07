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
sys.path.insert(0, str(ROOT))
from docket.ledger import make_record  # noqa: E402

DOCKET = ROOT / "bin" / "docket"


LEGACY = [
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
        "state": "open",
        "question": "Which validator?",
        "answer": "Undecided.",
        "because": [],
        "supersedes": [],
        "cost_if_wrong": "",
        "session": "",
        "author": "",
        "branch": "",
    },
]


def project(work: Path, records: list[dict]) -> Path:
    """A git repository holding a project-local ledger."""
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    ledger = work / ".docket" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("".join(json.dumps(r) + "\n" for r in records))
    return ledger


def run(work: Path, *argv: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, DOCKET_HOME=str(work / "global"), DOCKET_NO_UPDATE_CHECK="1")
    return subprocess.run(
        [sys.executable, str(DOCKET), *argv], cwd=work, capture_output=True, text=True, env=env
    )


def commit(work: Path) -> None:
    """Commit everything, so `--rewrite` sees tracked, clean files."""
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "add", "-A"], cwd=work, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "fixture"], cwd=work, check=True)


def rec(kind: str, ident: str, text: str, *, schema: int = 3, extra=None, **fields) -> dict:
    if kind == "decision":
        fields.setdefault("choice", "chosen")
    # make_record builds a new record, which never carries an audit field.
    audit = {key: fields.pop(key) for key in ("migrated_from",) if key in fields}
    record = make_record(
        kind, text, record_id=ident, ts="2026-09-12T00:00:00+00:00", author="tester", **fields
    )
    return {**record, "schema": schema, **audit, **(extra or {})}


class MigrateSchema3CliTests(unittest.TestCase):
    def schema2(self, work: Path) -> Path:
        return project(
            work,
            [
                rec("claim", "c1", "First claim", schema=2),
                rec("decision", "d2", "Use the first claim", schema=2, supports=[["c1"]]),
                rec("claim", "c3", "Second claim", schema=2),
                rec("decision", "d4", "Follows d2 and c3 and c9", schema=2, supports=[["c3"]]),
                rec("question", "q5", "What next", schema=2),
            ],
        )

    def test_the_default_output_is_a_summary_without_the_per_record_report(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = self.schema2(work)
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.splitlines()
            self.assertEqual(
                lines[0],
                "docket: migrated 5 records from schema 2 to schema 3 "
                "(2 claims, 2 decisions, 1 question)",
            )
            self.assertIn("rewrote 1 prose field", result.stdout)
            self.assertIn("left 1 unmapped id as written", result.stdout)
            self.assertIn(f"original kept at {ledger}.schema2", result.stdout)
            self.assertNotIn("d4 -> d2", result.stdout)
            self.assertNotIn("Follows", result.stdout)
            self.assertTrue(Path(str(ledger) + ".schema2").exists())

    def test_dry_run_prints_the_report_then_every_prose_change_and_unmapped_token(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = self.schema2(work)
            before = ledger.read_bytes()
            result = run(work, "migrate", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            out = result.stdout
            self.assertIn("d4 -> d2", out)
            self.assertIn("q5 -> q1", out)
            self.assertIn("d4 text: Follows d2 and c3 and c9 -> Follows d1 and c2 and c9", out)
            self.assertIn("d4 text: unmapped c9", out)
            self.assertLess(out.index("q5 -> q1"), out.index("d4 text:"))
            self.assertIn("docket: would migrate 5 records from schema 2 to schema 3", out)
            self.assertEqual(ledger.read_bytes(), before)
            self.assertFalse(Path(str(ledger) + ".schema2").exists())

    def test_rewrite_rewrites_the_named_files(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            self.schema2(work)
            doc = work / "notes.md"
            doc.write_text("d4 then d2, see c3. Keep c9.\n")
            untouched = work / "plain.md"
            untouched.write_text("nothing\n")
            commit(work)
            result = run(work, "migrate", "--rewrite", str(doc), str(untouched))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(doc.read_text(), "d2 then d1, see c2. Keep c9.\n")
            self.assertIn("rewrote 3 id mentions in 1 file", result.stdout)
            self.assertIn(str(doc), result.stdout)
            self.assertNotIn(str(untouched), result.stdout)

    def test_rewrite_with_dry_run_reports_files_and_counts_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            self.schema2(work)
            doc = work / "notes.md"
            doc.write_text("d4 then d2, see c3.\n")
            commit(work)
            result = run(work, "migrate", "--dry-run", "--rewrite", str(doc))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"{doc}: 3 ids", result.stdout)
            self.assertIn("would rewrite 3 id mentions in 1 file", result.stdout)
            self.assertEqual(doc.read_text(), "d4 then d2, see c3.\n")

    def test_rewrite_refuses_an_untracked_or_modified_file(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = self.schema2(work)
            doc = work / "notes.md"
            doc.write_text("d4\n")
            commit(work)
            fresh = work / "fresh.md"
            fresh.write_text("d4\n")
            before = ledger.read_bytes()
            result = run(work, "migrate", "--rewrite", str(doc), str(fresh))
            self.assertEqual(result.returncode, 2)
            self.assertIn("not tracked", result.stderr)
            self.assertNotIn("--emit-map", result.stderr)
            doc.write_text("d4 edited\n")
            result = run(work, "migrate", "--rewrite", str(doc))
            self.assertEqual(result.returncode, 2)
            self.assertIn("uncommitted", result.stderr)
            self.assertEqual(ledger.read_bytes(), before)

    def test_rewrite_is_refused_once_the_ledger_is_at_schema_3(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            self.schema2(work)
            doc = work / "notes.md"
            doc.write_text("d4\n")
            commit(work)
            self.assertEqual(run(work, "migrate").returncode, 0)
            result = run(work, "migrate", "--rewrite", str(doc))
            self.assertEqual(result.returncode, 2)
            self.assertIn("already at schema 3", result.stderr)
            self.assertNotIn("--emit-map", result.stderr)
            self.assertEqual(doc.read_text(), "d4\n")

    def test_map_and_emit_map_are_refused_on_a_schema_2_ledger(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = self.schema2(work)
            before = ledger.read_bytes()
            mapping = work / "map.json"
            mapping.write_text("{}")
            for argv in (("--map", str(mapping)), ("--emit-map", str(work / "out.json"))):
                result = run(work, "migrate", *argv)
                self.assertEqual(result.returncode, 2, argv)
                self.assertIn("schema 1", result.stderr)
                self.assertNotIn("then 'docket migrate --map", result.stderr)
            self.assertFalse((work / "out.json").exists())
            self.assertEqual(ledger.read_bytes(), before)

    def test_a_schema_1_ledger_still_gets_the_classification_hint_on_failure(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            project(work, [dict(LEGACY[0], state="parked")])
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 2)
            self.assertIn("--emit-map", result.stderr)


class OldIdTests(unittest.TestCase):
    def ledger(self, work: Path) -> None:
        # c1 and c3 both came from c4 on different branches. c2 came from c1,
        # and c1 is also a current id: the old id resolves to the new record.
        # c4 came from schema 1 as d9.
        project(
            work,
            [
                rec("claim", "c1", "First", branch="a", migrated_from="c4"),
                rec("claim", "c2", "Second", branch="a", migrated_from="c1"),
                rec("claim", "c3", "Third", branch="b", migrated_from="c4"),
                rec("claim", "c4", "Fourth", extra={"legacy": {"source_id": "d9"}}),
            ],
        )

    def test_show_names_the_command_that_finds_a_vanished_old_id(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            self.ledger(work)
            result = run(work, "show", "d9")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("no entry d9", result.stderr)
            self.assertIn("docket list --where was:d9", result.stderr)

    def test_show_is_silent_about_an_old_id_that_is_also_a_current_id(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            self.ledger(work)
            result = run(work, "show", "c1")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("First", result.stdout)
            self.assertEqual(result.stderr, "")

    def test_show_gives_no_hint_for_an_id_nobody_carried(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            self.ledger(work)
            result = run(work, "show", "c9")
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("was:", result.stderr)

    def test_list_finds_both_records_that_share_an_old_id(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            self.ledger(work)
            result = run(work, "list", "--where", "was:c4", "--json", "--legacy")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([r["id"] for r in json.loads(result.stdout)], ["c1", "c3"])
            narrowed = run(work, "list", "--where", "was:c4 branch:b", "--json")
            self.assertEqual([r["id"] for r in json.loads(narrowed.stdout)], ["c3"])

    def test_list_finds_a_record_by_its_schema_1_id(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            self.ledger(work)
            result = run(work, "list", "--where", "was:d9", "--json")
            self.assertEqual([r["id"] for r in json.loads(result.stdout)], ["c4"])


class MigrateCliTests(unittest.TestCase):
    def test_migration_converts_the_project_ledger(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, LEGACY)
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
            self.assertEqual([r["id"] for r in records], ["d1", "q1"])
            self.assertTrue(Path(str(ledger) + ".schema1").exists())

    def test_a_converted_ledger_lists(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            project(work, LEGACY)
            self.assertEqual(run(work, "migrate").returncode, 0)
            result = run(work, "list")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("d1", result.stdout)

    def test_a_schema_three_ledger_exits_clean_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, LEGACY)
            run(work, "migrate")
            after = ledger.read_bytes()
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already schema 3", result.stdout)
            self.assertEqual(ledger.read_bytes(), after)

    def test_a_schema_two_ledger_migrates_and_a_map_is_refused(self):
        records = [
            dict(
                json.loads(
                    json.dumps(
                        {
                            "schema": 2, "kind": "claim", "id": "c5", "text": "Premise",
                            "state": "accepted", "ts": "", "author": "", "session": "",
                            "branch": "", "scope": [], "rationale": "", "supports": [],
                            "depends_on": [], "answers": [], "supersedes": [], "evidence": [],
                            "revisit": "", "cost_if_wrong": "", "pinned": False,
                        }
                    )
                )
            )
        ]  # fmt: skip
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, records)
            refused = run(work, "migrate", "--emit-map", str(work / "map.json"))
            self.assertEqual(refused.returncode, 2)
            self.assertIn("applies to a schema 1 ledger", refused.stderr)
            result = run(work, "migrate")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("original kept at", result.stdout)
            self.assertTrue(Path(str(ledger) + ".schema2").exists())
            self.assertEqual(json.loads(ledger.read_text())["id"], "c1")

    def test_a_dry_run_reports_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            ledger = project(work, LEGACY)
            before = ledger.read_bytes()
            result = run(work, "migrate", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("d1 -> d1 decision/adopted", result.stdout)
            self.assertIn("d2 -> q1 question/open", result.stdout)
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
            project(work, records)
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
            project(work, records)
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
