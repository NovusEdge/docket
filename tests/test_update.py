import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import docket_update as up


class VersionCompare(unittest.TestCase):
    def test_minor_number_orders_numerically(self):
        self.assertTrue(up.is_newer("0.10.0", "0.9.0"))
        self.assertFalse(up.is_newer("0.9.0", "0.10.0"))

    def test_tag_prefix_is_stripped(self):
        self.assertTrue(up.is_newer("v0.11.0", "0.10.0"))

    def test_equal_versions_are_not_newer(self):
        self.assertFalse(up.is_newer("0.10.0", "v0.10.0"))

    def test_suffix_after_patch_is_ignored(self):
        self.assertFalse(up.is_newer("0.10.0-rc1", "0.10.0"))

    def test_unparseable_version_is_never_newer(self):
        self.assertFalse(up.is_newer("unknown", "0.10.0"))
        self.assertFalse(up.is_newer("0.11.0", "unknown"))


class StateFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["XDG_STATE_HOME"] = self.tmp.name
        self.addCleanup(os.environ.pop, "XDG_STATE_HOME", None)

    def test_absent_file_reads_as_empty(self):
        self.assertEqual(up.read_state(), {})

    def test_write_then_read_round_trips(self):
        up.write_state({"latest": "0.11.0", "next_check_at": 12.0})
        self.assertEqual(up.read_state()["latest"], "0.11.0")

    def test_malformed_file_reads_as_empty(self):
        up.state_path().parent.mkdir(parents=True, exist_ok=True)
        up.state_path().write_text("{not json")
        self.assertEqual(up.read_state(), {})

    def test_write_leaves_no_temporary_file_behind(self):
        up.write_state({"latest": "0.11.0"})
        self.assertEqual([p.name for p in up.state_dir().iterdir()], ["update.json"])

    def test_non_serializable_value_leaves_no_temporary_file_behind(self):
        with self.assertRaises(TypeError):
            up.write_state({"latest": object()})
        self.assertEqual(list(up.state_dir().iterdir()), [])

    def test_windows_state_dir_avoids_the_checkout_directory(self):
        os.environ.pop("XDG_STATE_HOME")
        os.environ["LOCALAPPDATA"] = r"C:\Users\a\AppData\Local"
        self.addCleanup(os.environ.pop, "LOCALAPPDATA", None)
        self.assertEqual(up.state_dir("win32").name, "docket-state")


class Shape(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_marker_wins_over_git_directory(self):
        (self.root / ".git").mkdir()
        (self.root / ".docket-managed").write_text("{}")
        self.assertEqual(up.shape(self.root), "managed")

    def test_git_directory_alone_is_a_source_tree(self):
        (self.root / ".git").mkdir()
        self.assertEqual(up.shape(self.root), "source")

    def test_claude_cache_copy_is_plugin_only(self):
        root = Path("/home/a/.claude/plugins/cache/NovusEdge/docket/0.8.0")
        self.assertEqual(up.plugin_origin(root), ("claude", "NovusEdge"))
        self.assertEqual(up.shape(root), "plugin")

    def test_codex_cache_copy_is_plugin_only(self):
        root = Path("/home/a/.codex/plugins/cache/local-personal/docket/0.8.0")
        self.assertEqual(up.plugin_origin(root), ("codex", "local-personal"))

    def test_bare_directory_is_unknown(self):
        self.assertEqual(up.shape(self.root), "unknown")


class Notice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".git").mkdir()

    def test_current_version_produces_no_notice(self):
        self.assertIsNone(up.notice("0.11.0", "0.11.0", self.root))

    def test_absent_latest_produces_no_notice(self):
        self.assertIsNone(up.notice("0.10.0", "", self.root))

    def test_checkout_notice_names_the_subcommand(self):
        line = up.notice("0.10.0", "0.11.0", self.root)
        self.assertIn("0.11.0 is available (running 0.10.0)", line)
        self.assertIn("Run: docket update", line)

    def test_claude_notice_names_the_harness_command_and_restart(self):
        root = Path("/home/a/.claude/plugins/cache/NovusEdge/docket/0.8.0")
        line = up.notice("0.8.0", "0.11.0", root)
        self.assertIn("claude plugin update docket@NovusEdge -y", line)
        self.assertIn("restart", line)
        self.assertNotIn("docket update", line.replace("docket@NovusEdge", ""))

    def test_codex_notice_uses_remove_then_add(self):
        root = Path("/home/a/.codex/plugins/cache/local-personal/docket/0.8.0")
        line = up.notice("0.8.0", "0.11.0", root)
        self.assertIn("codex plugin remove docket@local-personal", line)
        self.assertIn("codex plugin add docket@local-personal", line)

    def test_unknown_shape_names_the_repository(self):
        bare = Path(self.tmp.name) / "bare"
        bare.mkdir()
        self.assertIn("github.com/NovusEdge/docket", up.notice("0.8.0", "0.11.0", bare))


class Due(unittest.TestCase):
    def test_absent_state_is_due(self):
        self.assertTrue(up.due({}, now=1000.0))

    def test_future_next_check_is_not_due(self):
        self.assertFalse(up.due({"next_check_at": 2000.0}, now=1000.0))

    def test_past_next_check_is_due(self):
        self.assertTrue(up.due({"next_check_at": 500.0}, now=1000.0))

    def test_malformed_next_check_is_due(self):
        self.assertTrue(up.due({"next_check_at": "soon"}, now=1000.0))


class RunFetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["XDG_STATE_HOME"] = self.tmp.name
        self.addCleanup(os.environ.pop, "XDG_STATE_HOME", None)
        self.real = up.fetch_latest
        self.addCleanup(setattr, up, "fetch_latest", self.real)

    def test_lease_is_written_before_the_request(self):
        seen = {}

        def fetch(url=up.RELEASES_URL):
            seen["at_request"] = up.read_state().get("next_check_at")
            return "v0.11.0"

        up.fetch_latest = fetch
        up.run_fetch(now=1000.0)
        self.assertEqual(seen["at_request"], 1000.0 + up.LEASE_SECONDS)

    def test_success_records_latest_and_a_day_of_quiet(self):
        up.fetch_latest = lambda url=up.RELEASES_URL: "v0.11.0"
        self.assertEqual(up.run_fetch(now=1000.0), 0)
        state = up.read_state()
        self.assertEqual(state["latest"], "v0.11.0")
        self.assertEqual(state["checked_at"], 1000.0)
        self.assertEqual(state["next_check_at"], 1000.0 + up.SUCCESS_SECONDS)
        self.assertEqual(state["failures"], 0)

    def test_failure_backs_off_and_doubles(self):
        def boom(url=up.RELEASES_URL):
            raise OSError("no network")

        up.fetch_latest = boom
        up.run_fetch(now=1000.0)
        self.assertEqual(up.read_state()["next_check_at"], 1000.0 + up.FAILURE_SECONDS)
        up.run_fetch(now=2000.0)
        self.assertEqual(up.read_state()["next_check_at"], 2000.0 + 2 * up.FAILURE_SECONDS)

    def test_backoff_is_capped(self):
        up.write_state({"failures": 20})
        up.fetch_latest = lambda url=up.RELEASES_URL: (_ for _ in ()).throw(OSError())
        up.run_fetch(now=1000.0)
        self.assertEqual(up.read_state()["next_check_at"], 1000.0 + up.FAILURE_CAP)

    def test_failure_keeps_the_previous_latest(self):
        up.write_state({"latest": "v0.11.0"})
        up.fetch_latest = lambda url=up.RELEASES_URL: (_ for _ in ()).throw(OSError())
        up.run_fetch(now=1000.0)
        self.assertEqual(up.read_state()["latest"], "v0.11.0")


class SpawnFetch(unittest.TestCase):
    def test_child_gets_no_inherited_streams(self):
        recorded = {}

        class FakePopen:
            def __init__(self, argv, **kwargs):
                recorded["argv"] = argv
                recorded["kwargs"] = kwargs

        original = up.subprocess.Popen
        up.subprocess.Popen = FakePopen
        self.addCleanup(setattr, up.subprocess, "Popen", original)
        up.spawn_fetch(Path("/src/docket/bin/docket"))
        self.assertIn("_update-fetch", recorded["argv"])
        devnull = up.subprocess.DEVNULL
        self.assertEqual(recorded["kwargs"]["stdin"], devnull)
        self.assertEqual(recorded["kwargs"]["stdout"], devnull)
        self.assertEqual(recorded["kwargs"]["stderr"], devnull)

    def test_spawn_failure_is_swallowed(self):
        def boom(*a, **k):
            raise OSError("fork failed")

        original = up.subprocess.Popen
        up.subprocess.Popen = boom
        self.addCleanup(setattr, up.subprocess, "Popen", original)
        up.spawn_fetch(Path("/src/docket/bin/docket"))


import subprocess as sp

DOCKET = Path(__file__).resolve().parent.parent / "bin" / "docket"


class ContextNotice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.project = Path(self.tmp.name) / "project"
        (self.project / ".docket").mkdir(parents=True)
        (self.project / ".docket" / "ledger.jsonl").write_text("")

    def run_context(self, *args, **env):
        environment = {
            **os.environ,
            "XDG_STATE_HOME": str(self.state),
            "DOCKET_HOME": str(self.project / ".docket"),
            **env,
        }
        return sp.run([sys.executable, str(DOCKET), "context", *args],
                      cwd=self.project, env=environment,
                      capture_output=True, text=True)

    def seed(self, latest):
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "docket").mkdir(parents=True, exist_ok=True)
        (self.state / "docket" / "update.json").write_text(json.dumps(
            {"latest": latest, "checked_at": 0, "failures": 0,
             "next_check_at": 9_999_999_999}))

    def test_notice_prints_with_an_empty_ledger(self):
        self.seed("v99.0.0")
        done = self.run_context()
        self.assertIn("99.0.0 is available", done.stdout)

    def test_opt_out_suppresses_the_notice(self):
        self.seed("v99.0.0")
        done = self.run_context(DOCKET_NO_UPDATE_CHECK="1")
        self.assertNotIn("is available", done.stdout)

    def test_current_version_prints_nothing_extra(self):
        self.seed("v0.0.1")
        done = self.run_context()
        self.assertNotIn("is available", done.stdout)

    def test_notice_stays_inside_the_gemini_envelope(self):
        self.seed("v99.0.0")
        done = self.run_context("--for", "gemini")
        payload = json.loads(done.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("99.0.0 is available", context)


if __name__ == "__main__":
    unittest.main()
