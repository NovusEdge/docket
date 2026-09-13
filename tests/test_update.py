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


if __name__ == "__main__":
    unittest.main()
