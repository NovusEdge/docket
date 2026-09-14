"""Construct's SDK virtualenv. No network: uv is never actually run."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docket.construct import venv


class LocationTests(unittest.TestCase):
    def test_sits_under_the_global_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"DOCKET_HOME": tmp}):
                self.assertEqual(venv.root(), Path(tmp) / "venv")

    def test_packages_carries_this_interpreters_version(self):
        # Two interpreter versions must not share a directory: a venv built
        # before a distro upgrade holds wheels this process cannot import.
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"DOCKET_HOME": tmp}):
                site = venv.packages()
        self.assertIn(f"{sys.version_info.major}.{sys.version_info.minor}", str(site))

    def test_packages_sits_inside_the_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"DOCKET_HOME": tmp}):
                self.assertTrue(str(venv.packages()).startswith(str(venv.root())))

    def test_the_interpreter_sits_in_the_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"DOCKET_HOME": tmp}):
                self.assertEqual(venv.interpreter().parent.parent, venv.root())


class ActivateTests(unittest.TestCase):
    def home(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.dict("os.environ", {"DOCKET_HOME": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, sys, "path", list(sys.path))
        return Path(tmp.name)

    def test_reports_nothing_when_the_venv_is_absent(self):
        self.home()
        self.assertFalse(venv.activate())

    def test_appends_rather_than_inserts(self):
        # Someone who installed the SDK into their own environment keeps that
        # copy; the venv is the fallback, not the override.
        self.home()
        venv.packages().mkdir(parents=True)
        before = list(sys.path)
        self.assertTrue(venv.activate())
        self.assertEqual(sys.path[-1], str(venv.packages()))
        self.assertEqual(sys.path[: len(before)], before)

    def test_does_not_add_the_same_path_twice(self):
        self.home()
        venv.packages().mkdir(parents=True)
        venv.activate()
        venv.activate()
        self.assertEqual(sys.path.count(str(venv.packages())), 1)


class InstallTests(unittest.TestCase):
    def runs(self, returncode=0, stderr=""):
        """Collect the argv of every command install() would run."""
        calls = []

        def fake(argv, **_kw):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, returncode, "", stderr)

        return calls, fake

    def test_pins_the_venv_to_the_running_interpreter(self):
        # Without --python, uv may build against a Python it downloaded, and
        # the compiled dependencies would not import into this process.
        calls, fake = self.runs()
        with (
            patch.object(venv.shutil, "which", lambda _n: "/usr/bin/uv"),
            patch.object(venv.subprocess, "run", fake),
        ):
            venv.install("openai")
        self.assertEqual(calls[0][:4], ["uv", "venv", "--python", sys.executable])
        self.assertIn("--allow-existing", calls[0])

    def test_installs_the_bounded_spec_into_the_venv(self):
        calls, fake = self.runs()
        with (
            patch.object(venv.shutil, "which", lambda _n: "/usr/bin/uv"),
            patch.object(venv.subprocess, "run", fake),
        ):
            venv.install("anthropic")
        self.assertEqual(calls[1][:3], ["uv", "pip", "install"])
        self.assertEqual(calls[1][-1], venv.SPECS["anthropic"])
        self.assertIn(str(venv.interpreter()), calls[1])

    def test_every_sdk_construct_selects_has_a_bound(self):
        from docket.construct import client

        for spec in client.PROVIDERS.values():
            self.assertIn(spec["sdk"], venv.SPECS)

    def test_a_missing_uv_is_an_error_naming_it(self):
        with patch.object(venv.shutil, "which", lambda _n: None):
            with self.assertRaises(venv.VenvError) as caught:
                venv.install("openai")
        self.assertIn("uv", str(caught.exception))

    def test_a_failing_uv_reports_what_it_said(self):
        _calls, fake = self.runs(returncode=1, stderr="no such python")
        with (
            patch.object(venv.shutil, "which", lambda _n: "/usr/bin/uv"),
            patch.object(venv.subprocess, "run", fake),
        ):
            with self.assertRaises(venv.VenvError) as caught:
                venv.install("openai")
        self.assertIn("no such python", str(caught.exception))

    def test_a_missing_uv_binary_does_not_escape_as_oserror(self):
        def boom(argv, **_kw):
            raise OSError("Permission denied")

        with (
            patch.object(venv.shutil, "which", lambda _n: "/usr/bin/uv"),
            patch.object(venv.subprocess, "run", boom),
        ):
            with self.assertRaises(venv.VenvError):
                venv.install("openai")


class RemoveTests(unittest.TestCase):
    def test_deletes_the_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"DOCKET_HOME": tmp}):
                venv.packages().mkdir(parents=True)
                venv.remove()
                self.assertFalse(venv.root().exists())

    def test_an_absent_venv_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"DOCKET_HOME": tmp}):
                venv.remove()


if __name__ == "__main__":
    unittest.main()
