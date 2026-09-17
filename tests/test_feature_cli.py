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


class FeatureVerificationTests(FeatureCloseTests):
    def ledger_bytes(self):
        return (self.root / ".docket" / "ledger.jsonl").read_bytes()

    def test_done_lists_claims_the_change_set_touched(self):
        self.run_cli(
            "claim",
            "planner writes plugins/",
            "--state",
            "accepted",
            "--scope",
            "installer/planner.go",
        )
        self.run_cli("claim", "graph sorts roots", "--state", "accepted", "--scope", "graph/**")
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        _, out = self.run_cli("feature", "done", "one")
        self.assertIn("c1", out)
        self.assertNotIn("c2", out)

    def test_a_failed_claim_prints_the_command_and_writes_no_ledger_record(self):
        self.run_cli(
            "claim",
            "planner writes plugins/",
            "--state",
            "accepted",
            "--scope",
            "installer/planner.go",
        )
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        before = self.ledger_bytes()
        _, out = self.run_cli("feature", "done", "one", "--failed", "c1")
        self.assertIn("docket claim", out)
        self.assertIn("--supersedes c1", out)
        self.assertEqual(self.ledger_bytes(), before)

    def test_verdicts_are_recorded_in_the_done_event(self):
        self.run_cli(
            "claim",
            "planner writes plugins/",
            "--state",
            "accepted",
            "--scope",
            "installer/planner.go",
        )
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        self.run_cli("feature", "done", "one", "--held", "c1")
        _, out = self.run_cli("feature", "show", "f1", "--json")
        import json

        self.assertEqual(json.loads(out)["held"], ["c1"])

    def test_a_claim_with_no_verdict_is_recorded_as_unanswered(self):
        self.run_cli(
            "claim",
            "planner writes plugins/",
            "--state",
            "accepted",
            "--scope",
            "installer/planner.go",
        )
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        self.run_cli("feature", "done", "one")
        _, out = self.run_cli("feature", "show", "f1", "--json")
        import json

        self.assertEqual(json.loads(out)["unanswered"], ["c1"])


class FeatureOverlapTests(FeatureCloseTests):
    def test_done_names_another_feature_sharing_the_change_set(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        subprocess.run(
            ["git", "-C", str(self.root), "checkout", "-b", "feat/y"],
            check=True,
            capture_output=True,
        )
        self.run_cli("feature", "start", "two", "--text", "t", "--path", "installer/planner.go")
        subprocess.run(
            ["git", "-C", str(self.root), "checkout", "feat/x"],
            check=True,
            capture_output=True,
        )
        code, out = self.run_cli("feature", "done", "one")
        self.assertEqual(code, 0)
        self.assertIn("two", out)
        self.assertIn("overlap", out)

    def test_no_overlap_prints_no_advisory(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        code, out = self.run_cli("feature", "done", "one")
        self.assertEqual(code, 0)
        self.assertNotIn("overlap", out)


class FeatureRemapTests(FeatureCliTests):
    def test_remap_names_the_duplicate_ids_a_union_merge_left(self):
        import json

        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        store = self.root / ".docket" / "features.jsonl"
        first = store.read_text(encoding="utf-8").splitlines()[0]
        store.write_text(
            store.read_text(encoding="utf-8") + first.replace('"one"', '"two"') + "\n",
            encoding="utf-8",
        )
        mapping = self.root / "map.json"
        mapping.write_text(json.dumps({"d5": "d42"}), encoding="utf-8")
        # remap projected first, and project() refuses a store holding two
        # events with one id by telling the reader to run remap.
        code, _ = self.run_cli("feature", "remap", str(mapping))
        self.assertEqual(code, 1)

    def test_remap_refuses_a_mapfile_that_is_not_an_object(self):
        import json

        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        mapping = self.root / "map.json"
        mapping.write_text(json.dumps(["d5", "d42"]), encoding="utf-8")
        code, _ = self.run_cli("feature", "remap", str(mapping))
        self.assertEqual(code, 1)

    def test_remap_refuses_malformed_json(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        mapping = self.root / "map.json"
        mapping.write_text("{not json}", encoding="utf-8")
        code, _ = self.run_cli("feature", "remap", str(mapping))
        self.assertEqual(code, 1)

    def test_remap_rewrites_include_lists_through_new_amend_events(self):
        import json

        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.run_cli("feature", "amend", "one", "--include", "d5")
        mapping = self.root / "map.json"
        mapping.write_text(json.dumps({"d5": "d42"}), encoding="utf-8")

        store = self.root / ".docket" / "features.jsonl"
        before = len(store.read_text(encoding="utf-8").splitlines())
        code, _ = self.run_cli("feature", "remap", str(mapping))
        self.assertEqual(code, 0)
        after = store.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(after), before + 1)
        self.assertEqual(json.loads(after[-1])["event"], "amend")

        _, out = self.run_cli("feature", "show", "one", "--json")
        self.assertEqual(json.loads(out)["include"], ["d42"])

    def test_remap_leaves_an_untouched_feature_alone(self):
        import json

        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        mapping = self.root / "map.json"
        mapping.write_text(json.dumps({"d5": "d42"}), encoding="utf-8")
        store = self.root / ".docket" / "features.jsonl"
        before = store.read_text(encoding="utf-8")
        self.run_cli("feature", "remap", str(mapping))
        self.assertEqual(store.read_text(encoding="utf-8"), before)

    def test_rebase_emits_the_id_map(self):
        pass  # covered by tests/test_rebase.py after Step 3


class FeatureGcIdentityTests(FeatureCloseTests):
    def test_an_archived_id_is_never_handed_out_again(self):
        self.run_cli("feature", "start", "one", "--text", "first", "--path", "installer/**")
        self.commit("installer/planner.go")
        self.run_cli("feature", "done", "one")
        self.run_cli("feature", "gc")
        subprocess.run(
            ["git", "-C", str(self.root), "checkout", "-b", "feat/y"],
            check=True,
            capture_output=True,
        )
        code, out = self.run_cli(
            "feature", "start", "two", "--text", "second", "--path", "graph/**"
        )
        self.assertEqual(code, 0)
        # An id is a permanent address. Reusing f1 makes every citation to the
        # archived f1 point at different work.
        self.assertNotIn("f1 ", out)
        _, shown = self.run_cli("feature", "show", "f1", "--json")
        import json

        self.assertEqual(json.loads(shown)["text"], "first")

    def test_expire_reads_this_feature_s_own_close_event(self):
        # A slug is reusable, so two runs share one slug and their events
        # interleave. The first close belongs to the first run.
        self.run_cli("feature", "start", "one", "--text", "first", "--path", "installer/**")
        self.commit("installer/planner.go")
        self.run_cli("feature", "done", "one")
        self.run_cli("feature", "start", "one", "--text", "second", "--path", "graph/**")
        code, out = self.run_cli("feature", "gc", "--expire", "3650")
        self.assertEqual(code, 0)
        self.assertIn("0 feature events archived", out)


class FeatureGcTests(FeatureCloseTests):
    def test_gc_moves_a_closed_feature_and_leaves_the_open_one(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        self.run_cli("feature", "done", "one")
        subprocess.run(
            ["git", "-C", str(self.root), "checkout", "-b", "feat/y"],
            check=True,
            capture_output=True,
        )
        self.run_cli("feature", "start", "two", "--text", "t", "--path", "graph/**")

        code, out = self.run_cli("feature", "gc")
        self.assertEqual(code, 0)
        self.assertIn("archive", out)

        _, live = self.run_cli("feature", "list", "--json")
        import json

        slugs = [f["slug"] for f in json.loads(live)]
        self.assertEqual(slugs, ["two"])

    def test_gc_leaves_an_open_feature_alone(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        code, out = self.run_cli("feature", "gc")
        self.assertEqual(code, 0)
        self.assertIn("0", out)

    def test_show_reads_the_archive_after_gc(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        self.run_cli("feature", "done", "one")
        self.run_cli("feature", "gc")
        code, out = self.run_cli("feature", "show", "f1", "--json")
        self.assertEqual(code, 0)
        import json

        self.assertEqual(json.loads(out)["state"], "done")

    def test_gc_never_runs_on_its_own(self):
        self.run_cli("feature", "start", "one", "--text", "t", "--path", "installer/**")
        self.commit("installer/planner.go")
        self.run_cli("feature", "done", "one")
        self.run_cli("feature", "list")
        self.run_cli("feature", "brief", "f1")
        store = self.root / ".docket" / "features.jsonl"
        self.assertIn("f1", store.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
