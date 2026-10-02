import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


class SupersedeReasonCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        for args in (
            ("claim", "Writes are durable.", "--state", "accepted"),
            ("claim", "The queue is safe.", "--state", "accepted", "--supports", "c1"),
        ):
            out = run(self.cwd, *args)
            self.assertEqual(out.returncode, 0, out.stderr)

    def tearDown(self):
        self.tmp.cleanup()

    def show(self, ident):
        out = run(self.cwd, "show", ident, "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def supersede(self, *extra):
        return run(
            self.cwd,
            "claim",
            "Writes are durable after fsync.",
            "--state",
            "accepted",
            "--supersedes",
            "c1",
            *extra,
        )

    def test_a_reason_is_recorded(self):
        out = self.supersede("--supersede-reason", "restate")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.show("c3")["supersede_reason"], "restate")
        self.assertEqual(self.show("c2")["support"], "clean")

    def test_a_missing_reason_hints_and_flags(self):
        out = self.supersede()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("recorded as revise", out.stderr)
        self.assertEqual(self.show("c2")["support"], "flagged")

    def test_a_reason_without_supersedes_is_refused(self):
        out = run(self.cwd, "claim", "Another claim.", "--supersede-reason", "restate")
        self.assertEqual(out.returncode, 1)
        self.assertIn("--supersede-reason needs --supersedes", out.stderr)

    def test_review_clears_the_flag(self):
        self.supersede()
        out = run(self.cwd, "review", "c2", "--note", "fsync wording only")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("c2.r1", out.stdout)
        self.assertEqual(self.show("c2")["support"], "clean")

    def test_review_of_nothing_is_refused(self):
        before = (Path(self.cwd) / "global").rglob("ledger.jsonl")
        ledger_path = next(before)
        lines = ledger_path.read_text().count("\n")
        out = run(self.cwd, "review", "c2")
        self.assertEqual(out.returncode, 1)
        self.assertIn("nothing to review", out.stderr)
        self.assertEqual(ledger_path.read_text().count("\n"), lines)

    def test_review_of_an_unknown_id_is_refused(self):
        out = run(self.cwd, "review", "c9")
        self.assertEqual(out.returncode, 1)

    def test_correct_relabels_the_reason(self):
        self.supersede()
        out = run(self.cwd, "correct", "c3", "--supersede-reason", "restate", "--reason", "wording")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.show("c2")["support"], "clean")


if __name__ == "__main__":
    unittest.main()
