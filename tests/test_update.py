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


if __name__ == "__main__":
    unittest.main()
