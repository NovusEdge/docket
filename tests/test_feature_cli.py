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
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a/**")
        code, _ = self.run_cli("feature", "start", "one", "--text", "t", "--path", "b/**")
        self.assertEqual(code, 1)

    def test_amend_changes_the_status(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a/**")
        self.run_cli("feature", "amend", "one", "--status", "paused")
        _, out = self.run_cli("feature", "show", "one")
        self.assertIn("paused", out)

    def test_an_invalid_status_is_rejected_by_the_parser(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a/**")
        with self.assertRaises(SystemExit):
            self.run_cli("feature", "amend", "one", "--status", "urgent")

    def test_note_appears_in_show(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a/**")
        self.run_cli("feature", "note", "one", "a thing happened")
        _, out = self.run_cli("feature", "show", "one")
        self.assertIn("a thing happened", out)

    def test_list_json_is_machine_readable(self):
        import json

        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a/**")
        _, out = self.run_cli("feature", "list", "--json")
        self.assertEqual(json.loads(out)[0]["slug"], "one")


class FeatureCloseTests(FeatureCliTests):
    def commit(self, name, body="x\n"):
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_text(body, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", name], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-m", name], check=True, capture_output=True
        )

    def setUp(self):
        super().setUp()
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "t@example.test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "t"],
            check=True,
            capture_output=True,
        )
        self.commit("base.txt")
        subprocess.run(
            ["git", "-C", str(self.root), "checkout", "-b", "feat/x"],
            check=True,
            capture_output=True,
        )

    def test_done_splits_the_change_set(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        self.commit("graph/model.go")
        code, _ = self.run_cli("feature", "done", "one")
        self.assertEqual(code, 0)
        _, out = self.run_cli("feature", "show", "f1", "--json")
        import json

        feature = json.loads(out)
        self.assertEqual(feature["intentional"], ["installer/planner.go"])
        self.assertEqual(feature["unintentional"], ["graph/model.go"])
        self.assertEqual(feature["state"], "done")

    def test_done_refuses_a_dirty_working_tree(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.root), "add", "dirty.txt"], check=True, capture_output=True
        )
        code, _ = self.run_cli("feature", "done", "one")
        self.assertEqual(code, 1)

    def test_a_rename_out_of_the_declared_paths_is_recorded(self):
        self.commit("installer/planner.go")
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        (self.root / "graph").mkdir(exist_ok=True)
        subprocess.run(
            ["git", "-C", str(self.root), "mv", "installer/planner.go", "graph/planner.go"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-m", "move out"],
            check=True,
            capture_output=True,
        )
        self.run_cli("feature", "done", "one")
        _, out = self.run_cli("feature", "show", "f1", "--json")
        import json

        self.assertEqual(
            json.loads(out)["renamed_out"], ["installer/planner.go -> graph/planner.go"]
        )

    def test_one_branch_carries_one_active_feature(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        code, _ = self.run_cli("feature", "start", "two", "--text", "t", "--path", "graph/**")
        self.assertEqual(code, 1)

    def test_abandon_closes_without_a_change_set(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        code, _ = self.run_cli("feature", "abandon", "one", "--text", "went nowhere")
        self.assertEqual(code, 0)
        _, out = self.run_cli("feature", "show", "f1", "--json")
        import json

        feature = json.loads(out)
        self.assertEqual(feature["state"], "abandoned")
        self.assertEqual(feature["intentional"], [])


class FeatureCheckTests(FeatureCliTests):
    def test_check_passes_on_a_healthy_store(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a/**")
        code, _ = self.run_cli("check")
        self.assertEqual(code, 0)

    def test_check_reports_a_corrupt_feature_store(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a/**")
        store = self.root / ".docket" / "features.jsonl"
        store.write_text(store.read_text(encoding="utf-8") + "{not json}\n", encoding="utf-8")
        code, out = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("features.jsonl", out)

    def test_check_reports_a_duplicate_open_slug(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "a/**")
        store = self.root / ".docket" / "features.jsonl"
        first = store.read_text(encoding="utf-8").splitlines()[0]
        store.write_text(
            store.read_text(encoding="utf-8") + first.replace('"f1"', '"f2"') + "\n",
            encoding="utf-8",
        )
        code, out = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("already open", out)


class FeatureBriefTests(FeatureCliTests):
    def test_brief_resolves_the_active_feature_without_a_slug(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        code, out = self.run_cli("feature", "brief")
        self.assertEqual(code, 0)
        self.assertIn("one", out)

    def test_brief_names_a_slug_explicitly(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        code, out = self.run_cli("feature", "brief", "one")
        self.assertEqual(code, 0)
        self.assertIn("f1", out)

    def test_brief_with_no_active_feature_exits_one(self):
        code, _ = self.run_cli("feature", "brief")
        self.assertEqual(code, 1)


class FeatureIncludeExcludeTests(FeatureCliTests):
    def ledger_record(self, line):
        path = self.root / ".docket" / "ledger.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")

    def test_amend_records_include_and_exclude(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        code, _ = self.run_cli("feature", "amend", "one", "--exclude", "d1,d2")
        self.assertEqual(code, 0)
        _, out = self.run_cli("feature", "show", "one", "--json")
        import json

        self.assertEqual(json.loads(out)["exclude"], ["d1", "d2"])

    def test_check_reports_an_include_id_the_ledger_does_not_have(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.run_cli("feature", "amend", "one", "--include", "d404")
        code, out = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("d404", out)


class FeatureBlockedTests(FeatureCliTests):
    def test_a_feature_governed_by_a_blocked_decision_lists_as_blocked(self):
        (self.root / "installer").mkdir()
        (self.root / "installer" / "main.go").write_text("x\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.root), "add", "installer/main.go"],
            check=True,
            capture_output=True,
        )
        self.run_cli("claim", "a premise", "--state", "disputed", "--scope", "installer/**")
        self.run_cli(
            "decision",
            "pick one",
            "--choice",
            "this",
            "--scope",
            "installer/**",
            "--depends-on",
            "c1",
        )
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        _, out = self.run_cli("feature", "list")
        self.assertIn("blocked", out)

    def test_an_open_question_in_scope_does_not_block(self):
        self.run_cli("question", "still open", "--scope", "installer/**")
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        _, out = self.run_cli("feature", "list")
        self.assertNotIn("blocked", out)


if __name__ == "__main__":
    unittest.main()
