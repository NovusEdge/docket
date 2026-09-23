import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from docket import ledger  # noqa: E402,F401

DOCKET = str(Path(__file__).resolve().parent.parent / "bin" / "docket")


def run(cwd, *args):
    env = dict(os.environ)
    env["DOCKET_HOME"] = str(Path(cwd) / "global")
    env["DOCKET_AUTHOR"] = "test"
    env["DOCKET_NO_UPDATE_CHECK"] = "1"
    env["XDG_STATE_HOME"] = str(Path(cwd) / "state")
    return subprocess.run(
        [sys.executable, DOCKET, *args], cwd=cwd, env=env, capture_output=True, text=True
    )


class CorrectCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        out = run(self.cwd, "decision", "The cache lives in Redis.", "--choice", "Redis",
                  "--scope", "lib/cache.py")
        self.assertEqual(out.returncode, 0, out.stderr)

    def tearDown(self):
        self.tmp.cleanup()

    def show(self, ident):
        out = run(self.cwd, "show", ident, "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_correct_replaces_a_field_and_keeps_the_id(self):
        out = run(self.cwd, "correct", "d1", "--scope", "docket/cache.py", "--reason", "moved")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(out.stdout.startswith("d1.1"))
        record = self.show("d1")
        self.assertEqual(record["scope"], ["docket/cache.py"])
        self.assertEqual(record["corrections"], ["d1.1"])
        self.assertEqual(record["original"], {"scope": ["lib/cache.py"]})

    def test_clear_empties_a_list_field(self):
        run(self.cwd, "correct", "d1", "--clear", "scope")
        self.assertEqual(self.show("d1")["scope"], [])

    def test_clear_and_set_of_one_field_conflict(self):
        out = run(self.cwd, "correct", "d1", "--clear", "scope", "--scope", "a.py")
        self.assertEqual(out.returncode, 1)
        self.assertIn("conflict", out.stderr)

    def test_a_correction_needs_a_field(self):
        out = run(self.cwd, "correct", "d1")
        self.assertEqual(out.returncode, 1)
        self.assertIn("at least one field", out.stderr)

    def test_choice_is_refused_with_a_pointer_to_supersession(self):
        out = run(self.cwd, "correct", "d1", "--choice", "Postgres")
        self.assertEqual(out.returncode, 1)
        self.assertIn("--supersedes", out.stderr)
        self.assertNotIn("corrections", self.show("d1"))

    def test_question_text_is_refused(self):
        out = run(self.cwd, "correct", "d1", "--text", "Where does the cache live?")
        self.assertEqual(out.returncode, 1)
        self.assertIn("not ask it", out.stderr)

    def test_unknown_target_is_refused(self):
        out = run(self.cwd, "correct", "d9", "--scope", "a.py")
        self.assertEqual(out.returncode, 1)
        self.assertIn("unknown or later", out.stderr)

    def test_clear_alternatives_names_the_real_flag(self):
        out = run(self.cwd, "correct", "d1", "--clear", "alternatives", "--alternative", "Postgres")
        self.assertEqual(out.returncode, 1)
        self.assertIn("--alternative", out.stderr)
        self.assertNotIn("--alternatives", out.stderr)

    def test_a_malformed_id_is_refused_before_anything_else(self):
        out = run(self.cwd, "correct", "d1.1", "--scope", "a.py")
        self.assertEqual(out.returncode, 1)
        self.assertIn("correct names a claim, decision, or question id", out.stderr)

    def test_state_is_refused_with_a_pointer_to_supersession(self):
        out = run(self.cwd, "correct", "d1", "--state", "adopted")
        self.assertEqual(out.returncode, 1)
        self.assertIn("--supersedes", out.stderr)
        self.assertNotIn("corrections", self.show("d1"))

    def test_supersedes_is_refused_with_a_pointer_to_supersession(self):
        out = run(self.cwd, "correct", "d1", "--supersedes", "d1")
        self.assertEqual(out.returncode, 1)
        self.assertIn("--supersedes", out.stderr)
        self.assertNotIn("corrections", self.show("d1"))

    def test_decision_only_field_is_refused_on_a_claim(self):
        run(self.cwd, "claim", "Writes are durable.")
        out = run(self.cwd, "correct", "c2", "--alternative", "x")
        self.assertEqual(out.returncode, 1)
        self.assertIn("decision-only field", out.stderr)

    def test_repeating_a_pin_refuses_as_a_no_op(self):
        run(self.cwd, "correct", "d1", "--pin")
        out = run(self.cwd, "correct", "d1", "--pin")
        self.assertEqual(out.returncode, 1)
        self.assertIn("nothing to correct", out.stderr)
        self.assertEqual(self.show("d1")["corrections"], ["d1.1"])

    def test_a_no_op_field_alongside_a_real_change_writes_only_the_real_field(self):
        out = run(self.cwd, "correct", "d1", "--scope", "lib/cache.py", "--rationale", "Fast.")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = self.show("d1.1")
        self.assertEqual(data["fields"], {"rationale": "Fast."})

    def test_pin_and_unpin(self):
        run(self.cwd, "correct", "d1", "--pin")
        self.assertTrue(self.show("d1")["pinned"])
        run(self.cwd, "correct", "d1", "--unpin")
        self.assertFalse(self.show("d1")["pinned"])

    def test_show_prints_the_correction_line(self):
        run(self.cwd, "correct", "d1", "--scope", "docket/cache.py", "--reason", "moved")
        out = run(self.cwd, "show", "d1.1")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("corrects d1", out.stdout)
        self.assertIn('["lib/cache.py"] -> ["docket/cache.py"]', out.stdout)
        self.assertIn("Reason: moved", out.stdout)
        data = self.show("d1.1")
        self.assertEqual(data["before"], {"scope": ["lib/cache.py"]})

    def test_show_lists_corrections_on_the_record(self):
        run(self.cwd, "correct", "d1", "--scope", "a.py")
        run(self.cwd, "correct", "d1", "--scope", "b.py")
        out = run(self.cwd, "show", "d1")
        self.assertIn("Corrections: d1.1, d1.2", out.stdout)

    def test_show_at_a_point_before_the_correction(self):
        run(self.cwd, "claim", "Writes are durable.")
        run(self.cwd, "correct", "d1", "--scope", "a.py")
        self.assertEqual(self.show("d1")["scope"], ["a.py"])
        out = run(self.cwd, "show", "d1", "--json", "--at", "c2")
        self.assertEqual(json.loads(out.stdout)["scope"], ["lib/cache.py"])
        out = run(self.cwd, "show", "d1", "--json", "--at", "d1.1")
        self.assertEqual(json.loads(out.stdout)["scope"], ["a.py"])


class ContextCmdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_context_since_a_correction_token_reports_no_change(self):
        out = run(self.cwd, "decision", "The cache lives in Redis.", "--choice", "Redis")
        self.assertEqual(out.returncode, 0, out.stderr)
        out = run(self.cwd, "correct", "d1", "--scope", "docket/cache.py")
        self.assertEqual(out.returncode, 0, out.stderr)
        out = run(self.cwd, "context", "--no-auto-scope")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("latest: d1.1@", out.stdout)
        token = re.search(r"latest: (d1\.1@[0-9a-f]+)", out.stdout).group(1)
        out = run(self.cwd, "context", "--no-auto-scope", "--since", token)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("# changed: 0 added, 0 corrected, 0 no longer available.", out.stdout)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        subprocess.run(["git", "init", "-q"], cwd=self.cwd, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
             "--allow-empty", "-m", "init"],
            cwd=self.cwd, check=True,
        )
        run(self.cwd, "decision", "The cache lives in Redis.", "--choice", "Redis")
        run(self.cwd, "correct", "d1", "--scope", "a.py")
        self.path = Path(run(self.cwd, "where").stdout.split("  (")[0])

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_accepts_a_correction(self):
        out = run(self.cwd, "check")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("reads cleanly", out.stdout)
        self.assertIn("1 record and 1 correction", out.stdout)

    def test_check_reports_a_malformed_correction(self):
        with self.path.open("a") as stream:
            stream.write(json.dumps({"schema": 2, "kind": "correction", "id": "d1.2",
                                     "corrects": "d1", "fields": {"choice": "x"}, "reason": "",
                                     "ts": "", "author": "", "session": "", "branch": ""}) + "\n")
        out = run(self.cwd, "check")
        self.assertEqual(out.returncode, 1)
        self.assertIn("line 3", out.stdout)
        self.assertIn("choice", out.stdout)

    def test_check_reports_a_feature_naming_a_correction(self):
        store = self.path.parent / "features.jsonl"
        out = run(self.cwd, "feature", "start", "cache", "--text", "Cache work", "--path", "src/")
        self.assertEqual(out.returncode, 0, out.stderr)
        out = run(self.cwd, "feature", "amend", "cache", "--include", "d1.1")
        self.assertEqual(out.returncode, 0, out.stderr)
        out = run(self.cwd, "check")
        self.assertEqual(out.returncode, 1)
        self.assertIn("include names d1.1", out.stdout)
        self.assertTrue(store.exists())


if __name__ == "__main__":
    unittest.main()
