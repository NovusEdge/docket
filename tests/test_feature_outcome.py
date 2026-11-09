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

    def commit(self, name):
        (self.root / name).write_text(f"{name}\n", encoding="utf-8")
        git(self.root, "add", name)
        git(self.root, "commit", "-m", name)
        return subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

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

    def test_fork_point_prefers_origin_main_over_a_stale_local_main(self):
        git(self.root, "checkout", "-b", "upstream")
        fresh = self.commit("upstream.txt")
        git(self.root, "update-ref", "refs/remotes/origin/main", fresh)
        git(self.root, "checkout", "-b", "feat/x", "origin/main")
        self.commit("work.txt")

        sha, warning = outcome.fork_point(self.root)
        self.assertEqual(sha, fresh)
        self.assertEqual(warning, "")

    def test_fork_point_with_only_a_local_main_is_unchanged(self):
        git(self.root, "checkout", "-b", "feat/x")
        self.commit("work.txt")
        git(self.root, "checkout", "main")
        self.commit("upstream.txt")
        git(self.root, "checkout", "feat/x")
        expected = subprocess.run(
            ["git", "-C", str(self.root), "merge-base", "HEAD", "main"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        sha, warning = outcome.fork_point(self.root)
        self.assertEqual(sha, expected)
        self.assertEqual(warning, "")

    def test_fork_point_prefers_a_newer_local_main_over_origin_main(self):
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")
        fresh = self.commit("upstream.txt")
        git(self.root, "checkout", "-b", "feat/x")
        self.commit("work.txt")
        self.assertEqual(outcome.fork_point(self.root), (fresh, ""))

    def test_fork_point_prefers_the_remote_base_when_default_branches_diverge(self):
        git(self.root, "checkout", "-b", "upstream")
        remote = self.commit("upstream.txt")
        git(self.root, "update-ref", "refs/remotes/origin/main", remote)
        git(self.root, "checkout", "main")
        self.commit("local.txt")
        git(self.root, "checkout", "-b", "feat/x")
        git(self.root, "merge", "origin/main", "-m", "merge")
        self.assertEqual(outcome.fork_point(self.root), (remote, ""))

    def test_fork_point_uses_origin_head_for_a_custom_default_branch(self):
        git(self.root, "checkout", "-b", "upstream")
        fresh = self.commit("upstream.txt")
        git(self.root, "update-ref", "refs/remotes/origin/trunk", fresh)
        git(self.root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        git(self.root, "checkout", "-b", "feat/x", "origin/trunk")
        self.commit("work.txt")
        self.assertEqual(outcome.fork_point(self.root), (fresh, ""))

    def test_fork_point_skips_an_unresolved_origin_head(self):
        git(self.root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/missing")
        git(self.root, "checkout", "-b", "upstream")
        fresh = self.commit("upstream.txt")
        git(self.root, "update-ref", "refs/remotes/origin/master", fresh)
        git(self.root, "checkout", "-b", "feat/x", "origin/master")
        self.commit("work.txt")
        self.assertEqual(outcome.fork_point(self.root), (fresh, ""))

    def test_fork_point_on_local_main_with_a_remote_returns_head_and_warns(self):
        head = self.commit("local.txt")
        git(self.root, "checkout", "-b", "upstream")
        fresh = self.commit("upstream.txt")
        git(self.root, "update-ref", "refs/remotes/origin/main", fresh)
        git(self.root, "checkout", "main")
        sha, warning = outcome.fork_point(self.root)
        self.assertEqual(sha, head)
        self.assertIn("recording HEAD as the base", warning)

    def test_fork_point_detached_at_the_remote_default_tip_returns_head_and_warns(self):
        git(self.root, "checkout", "-b", "upstream")
        head = self.commit("upstream.txt")
        git(self.root, "update-ref", "refs/remotes/origin/main", head)
        git(self.root, "checkout", "--detach", "origin/main")
        sha, warning = outcome.fork_point(self.root)
        self.assertEqual(sha, head)
        self.assertIn("recording HEAD as the base", warning)

    def test_fork_point_on_a_new_branch_at_the_remote_default_tip_does_not_warn(self):
        git(self.root, "checkout", "-b", "upstream")
        head = self.commit("upstream.txt")
        git(self.root, "update-ref", "refs/remotes/origin/main", head)
        git(self.root, "checkout", "-b", "feat/x", "origin/main")
        self.assertEqual(outcome.fork_point(self.root), (head, ""))

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

    def test_merging_the_branch_into_the_default_branch_keeps_its_change_set(self):
        git(self.root, "checkout", "-b", "feat/x")
        base, _ = outcome.fork_point(self.root)
        (self.root / "work.txt").write_text("work\n", encoding="utf-8")
        git(self.root, "add", "work.txt")
        git(self.root, "commit", "-m", "work")
        git(self.root, "checkout", "main")
        git(self.root, "merge", "feat/x", "-m", "merge")
        git(self.root, "checkout", "feat/x")
        changed, _ = outcome.changed_files(self.root, base)
        self.assertEqual(changed, ["work.txt"])

    def test_a_feature_with_no_base_cannot_be_closed(self):
        with self.assertRaisesRegex(outcome.OutcomeError, "no base commit"):
            outcome.changed_files(self.root, "")

    def test_a_bare_scope_is_refused_before_it_can_match_nothing(self):
        import docket.features as features

        for bad in ("Makefile", "installer", "a"):
            with self.assertRaisesRegex(features.FeatureError, "can never match"):
                features.make_event("start", "one", text="t", paths=[bad])

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
