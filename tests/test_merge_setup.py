import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from docket import merge_setup


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class SetupTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def config(self):
        r = subprocess.run(
            ["git", "config", "--local", "--get", "merge.docket.driver"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        return r.stdout.strip()

    def attributes(self):
        return (self.root / ".gitattributes").read_text(encoding="utf-8").splitlines()

    def test_setup_writes_the_attribute_and_the_config(self):
        with mock.patch("shutil.which", return_value="/usr/bin/docket"):
            merge_setup.setup(self.root)
        self.assertIn(merge_setup.ATTRIBUTE, self.attributes())
        self.assertEqual(self.config(), merge_setup.DRIVER)

    def test_setup_writes_no_driver_name(self):
        with mock.patch("shutil.which", return_value="/usr/bin/docket"):
            merge_setup.setup(self.root)
        r = subprocess.run(
            ["git", "config", "--local", "--get", "merge.docket.name"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(r.returncode, 0)

    def test_a_failing_git_config_reports_failure_not_registration(self):
        real = merge_setup._git
        failed = subprocess.CompletedProcess([], 1, "", "error: could not lock config file")

        def fake(root, *args):
            return failed if args and args[0] == "config" else real(root, *args)

        with (
            mock.patch("shutil.which", return_value="/usr/bin/docket"),
            mock.patch.object(merge_setup, "_git", fake),
        ):
            messages = merge_setup.setup(self.root)
        self.assertFalse(any("registered the" in m for m in messages), messages)
        self.assertTrue(any("not registered" in m and "could not lock" in m for m in messages))

    def test_a_non_utf8_gitattributes_does_not_raise(self):
        (self.root / ".gitattributes").write_bytes(b"\xff\xfe\x00bad\n")
        with mock.patch("shutil.which", return_value="/usr/bin/docket"):
            messages = merge_setup.setup(self.root)
        self.assertTrue(any(".gitattributes" in m for m in messages), messages)

    def test_running_setup_twice_leaves_one_attribute_line(self):
        with mock.patch("shutil.which", return_value="/usr/bin/docket"):
            merge_setup.setup(self.root)
            merge_setup.setup(self.root)
        self.assertEqual(self.attributes().count(merge_setup.ATTRIBUTE), 1)

    def test_a_union_line_stays_and_the_ledger_line_follows_it(self):
        (self.root / ".gitattributes").write_text(".docket/*.jsonl merge=union\n")
        with mock.patch("shutil.which", return_value="/usr/bin/docket"):
            merge_setup.setup(self.root)
        lines = self.attributes()
        self.assertLess(
            lines.index(".docket/*.jsonl merge=union"), lines.index(merge_setup.ATTRIBUTE)
        )

    def test_without_docket_on_path_nothing_is_registered(self):
        with mock.patch("shutil.which", return_value=None):
            messages = merge_setup.setup(self.root)
        self.assertEqual(self.config(), "")
        self.assertTrue(any("PATH" in m for m in messages), messages)

    def test_notice_when_the_attribute_is_set_but_the_config_is_missing(self):
        (self.root / ".gitattributes").write_text(merge_setup.ATTRIBUTE + "\n")
        self.assertIn("docket init", merge_setup.notice(self.root) or "")

    def test_notice_when_the_configured_command_does_not_resolve(self):
        (self.root / ".gitattributes").write_text(merge_setup.ATTRIBUTE + "\n")
        subprocess.run(
            ["git", "config", "merge.docket.driver", "no-such-docket merge-driver %O %A %B"],
            cwd=self.root,
            check=True,
        )
        self.assertIsNotNone(merge_setup.notice(self.root))

    def test_no_notice_when_set_up(self):
        with mock.patch("shutil.which", return_value="/usr/bin/docket"):
            merge_setup.setup(self.root)
            self.assertIsNone(merge_setup.notice(self.root))

    def test_no_notice_without_the_attribute(self):
        self.assertIsNone(merge_setup.notice(self.root))

    def test_setup_works_in_a_linked_worktree(self):
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "x",
            ],
            cwd=self.root,
            check=True,
        )
        linked = self.root / "wt"
        subprocess.run(["git", "worktree", "add", "-q", str(linked)], cwd=self.root, check=True)
        with mock.patch("shutil.which", return_value="/usr/bin/docket"):
            merge_setup.setup(linked)
        self.assertIn(merge_setup.ATTRIBUTE, (linked / ".gitattributes").read_text().splitlines())


class OutsideGitTests(unittest.TestCase):
    def test_setup_outside_a_repository_does_nothing(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        self.assertEqual(merge_setup.setup(root), [])
        self.assertFalse((root / ".gitattributes").exists())
        self.assertIsNone(merge_setup.notice(root))
