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
from docket.cli.autoscope import uncommitted_paths
from docket.cli.context_cmd import _NO_FEATURE_HINT, _feature_block


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class NoFeatureHintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.email", "t@example.test")
        git(self.root, "config", "user.name", "t")
        (self.root / ".docket").mkdir()
        (self.root / ".docket" / "ledger.jsonl").write_text("", encoding="utf-8")
        self.cwd = Path.cwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def block(self):
        return _feature_block(self.root, [])

    def test_a_dirty_tree_with_no_feature_store_gets_the_hint(self):
        (self.root / "work.txt").write_text("x\n", encoding="utf-8")
        self.assertEqual(self.block(), _NO_FEATURE_HINT)

    def test_a_staged_change_gets_the_hint(self):
        (self.root / "work.txt").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "work.txt")
        git(self.root, "commit", "-m", "base")
        (self.root / "work.txt").write_text("y\n", encoding="utf-8")
        git(self.root, "add", "work.txt")
        self.assertEqual(self.block(), _NO_FEATURE_HINT)

    def test_a_gitignored_file_gets_no_hint(self):
        (self.root / ".gitignore").write_text("out/\n", encoding="utf-8")
        git(self.root, "add", ".gitignore")
        git(self.root, "commit", "-m", "base")
        (self.root / "out").mkdir()
        (self.root / "out" / "build.bin").write_text("x\n", encoding="utf-8")
        self.assertEqual(self.block(), "")

    def test_changes_only_under_docket_get_no_hint(self):
        self.assertEqual(self.block(), "")

    def test_a_clean_tree_gets_no_hint(self):
        (self.root / "work.txt").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "base")
        self.assertEqual(self.block(), "")

    def test_many_docket_paths_cannot_hide_a_change_elsewhere(self):
        (self.root / ".docket" / "archive").mkdir()
        for i in range(60):
            (self.root / ".docket" / "archive" / f"a{i}.jsonl").write_text("", encoding="utf-8")
        (self.root / "zzz.txt").write_text("x\n", encoding="utf-8")
        self.assertEqual(self.block(), _NO_FEATURE_HINT)
        self.assertGreater(len(uncommitted_paths()), 50)

    def test_an_open_feature_prints_its_brief_and_no_hint(self):
        with redirect_stdout(io.StringIO()):
            code = main(["feature", "start", "one", "--text", "do the thing", "--path", "a/**"])
        self.assertEqual(code, 0)
        (self.root / "work.txt").write_text("x\n", encoding="utf-8")
        block = self.block()
        self.assertIn("one", block)
        self.assertNotIn("none open", block)

    def test_a_paused_feature_counts_as_open(self):
        with redirect_stdout(io.StringIO()):
            main(["feature", "start", "one", "--text", "t", "--path", "a/**"])
            main(["feature", "amend", "one", "--status", "paused"])
        (self.root / "work.txt").write_text("x\n", encoding="utf-8")
        self.assertNotEqual(self.block(), _NO_FEATURE_HINT)

    def test_outside_a_repository_there_is_no_hint_and_no_error(self):
        with tempfile.TemporaryDirectory() as bare:
            os.chdir(bare)
            try:
                self.assertEqual(_feature_block(Path(bare), []), "")
            finally:
                os.chdir(self.root)

    def test_a_missing_git_binary_degrades_to_no_hint(self):
        (self.root / "work.txt").write_text("x\n", encoding="utf-8")
        old = os.environ["PATH"]
        os.environ["PATH"] = ""
        try:
            self.assertEqual(self.block(), "")
        finally:
            os.environ["PATH"] = old


if __name__ == "__main__":
    unittest.main()
