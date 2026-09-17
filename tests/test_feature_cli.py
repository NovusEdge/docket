import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from docket.cli import main


class FeatureCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(
            ["git", "-C", str(self.root), "init", "-b", "main"], check=True, capture_output=True
        )
        (self.root / ".docket").mkdir()
        (self.root / ".docket" / "ledger.jsonl").write_text("", encoding="utf-8")
        self.cwd = Path.cwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_cli(self, *argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(list(argv))
        return code, buffer.getvalue()

    def test_start_records_a_feature_and_list_shows_it(self):
        code, _ = self.run_cli(
            "feature", "start", "one", "--text", "do the thing", "--path", "installer/**"
        )
        self.assertEqual(code, 0)
        code, out = self.run_cli("feature", "list")
        self.assertEqual(code, 0)
        self.assertIn("one", out)
        self.assertIn("active", out)

    def test_a_duplicate_start_is_refused(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a")
        code, _ = self.run_cli("feature", "start", "one", "--text", "t", "--path", "b")
        self.assertEqual(code, 1)

    def test_amend_changes_the_status(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a")
        self.run_cli("feature", "amend", "one", "--status", "paused")
        _, out = self.run_cli("feature", "show", "one")
        self.assertIn("paused", out)

    def test_an_invalid_status_is_rejected_by_the_parser(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a")
        with self.assertRaises(SystemExit):
            self.run_cli("feature", "amend", "one", "--status", "urgent")

    def test_note_appears_in_show(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a")
        self.run_cli("feature", "note", "one", "a thing happened")
        _, out = self.run_cli("feature", "show", "one")
        self.assertIn("a thing happened", out)

    def test_list_json_is_machine_readable(self):
        import json

        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a")
        _, out = self.run_cli("feature", "list", "--json")
        self.assertEqual(json.loads(out)[0]["slug"], "one")


if __name__ == "__main__":
    unittest.main()
