import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.feature_outcome as outcome


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class ClassifyTests(unittest.TestCase):
    def test_a_file_under_a_declared_glob_is_intentional(self):
        intentional, unintentional = outcome.classify(
            ["installer/**"], ["installer/planner.go", "graph/model.go"]
        )
        self.assertEqual(intentional, ["installer/planner.go"])
        self.assertEqual(unintentional, ["graph/model.go"])

    def test_an_exact_path_matches(self):
        intentional, _ = outcome.classify(["docs/installation.md"], ["docs/installation.md"])
        self.assertEqual(intentional, ["docs/installation.md"])

    def test_a_file_created_after_start_still_matches_its_glob(self):
        intentional, unintentional = outcome.classify(["installer/**"], ["installer/brand-new.go"])
        self.assertEqual(intentional, ["installer/brand-new.go"])
        self.assertEqual(unintentional, [])


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.email", "t@example.test")
        git(self.root, "config", "user.name", "t")
        (self.root / "base.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "base.txt")
        git(self.root, "commit", "-m", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def test_fork_point_on_the_default_branch_returns_head_and_warns(self):
        sha, warning = outcome.fork_point(self.root)
        self.assertTrue(sha)
        self.assertIn("default branch", warning)

    def test_fork_point_on_a_branch_is_the_merge_base(self):
        head = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        git(self.root, "checkout", "-b", "feat/x")
        (self.root / "work.txt").write_text("work\n", encoding="utf-8")
        git(self.root, "add", "work.txt")
        git(self.root, "commit", "-m", "work")
        sha, warning = outcome.fork_point(self.root)
        self.assertEqual(sha, head)
        self.assertEqual(warning, "")

    def test_merging_the_default_branch_adds_nothing_to_the_change_set(self):
        git(self.root, "checkout", "-b", "feat/x")
        (self.root / "work.txt").write_text("work\n", encoding="utf-8")
        git(self.root, "add", "work.txt")
        git(self.root, "commit", "-m", "work")
        base, _ = outcome.fork_point(self.root)
        git(self.root, "checkout", "main")
        (self.root / "upstream.txt").write_text("upstream\n", encoding="utf-8")
        git(self.root, "add", "upstream.txt")
        git(self.root, "commit", "-m", "upstream")
        git(self.root, "checkout", "feat/x")
        git(self.root, "merge", "main", "-m", "merge")
        changed, _ = outcome.changed_files(self.root, base)
        self.assertEqual(changed, ["work.txt"])

    def test_a_rename_is_reported_as_a_rename(self):
        git(self.root, "checkout", "-b", "feat/x")
        base, _ = outcome.fork_point(self.root)
        git(self.root, "mv", "base.txt", "moved.txt")
        git(self.root, "commit", "-m", "move")
        changed, renames = outcome.changed_files(self.root, base)
        self.assertEqual(renames, [("base.txt", "moved.txt")])
        self.assertIn("moved.txt", changed)


if __name__ == "__main__":
    unittest.main()
