import hashlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = load("docket_bootstrap", HERE / "install.py")

    def test_platform_asset_mapping(self):
        cases = [
            ("linux", "x86_64", "docket-installer-linux-amd64"),
            ("linux", "aarch64", "docket-installer-linux-arm64"),
            ("darwin", "arm64", "docket-installer-darwin-arm64"),
            ("win32", "AMD64", "docket-installer-windows-amd64.exe"),
        ]
        for platform, machine, expected in cases:
            self.assertEqual(self.bootstrap.asset_name(platform, machine), expected)
        with self.assertRaisesRegex(RuntimeError, "unsupported platform"):
            self.bootstrap.asset_name("freebsd", "amd64")

    def test_download_uses_release_urls_verifies_checksum_and_preserves_args(self):
        payload = b"same-go-binary"
        digest = hashlib.sha256(payload).hexdigest()
        opened = []

        def urlopen(url):
            opened.append(url)
            if url.endswith("SHA256SUMS"):
                return io.BytesIO((digest + "  docket-installer-linux-amd64\n").encode())
            return io.BytesIO(payload)

        calls = []
        with mock.patch.object(self.bootstrap.urllib.request, "urlopen", side_effect=urlopen), \
             mock.patch.object(self.bootstrap.subprocess, "call", side_effect=lambda cmd, cwd=None: calls.append((cmd, cwd)) or 7):
            rc = self.bootstrap.launch(["--dry-run", "--yes", "--update"], script=Path("/tmp/install.py"),
                                       platform="linux", machine="x86_64", cwd="/caller")
        self.assertEqual(rc, 7)
        self.assertEqual(opened, [
            "https://github.com/NovusEdge/docket/releases/latest/download/SHA256SUMS",
            "https://github.com/NovusEdge/docket/releases/latest/download/docket-installer-linux-amd64",
        ])
        self.assertEqual(calls[0][0][1:], ["--dry-run", "--yes", "--update"])
        self.assertEqual(calls[0][1], "/caller")

    def test_version_override_selects_tagged_release(self):
        payload = b"binary"
        digest = hashlib.sha256(payload).hexdigest()
        with mock.patch.dict(os.environ, {"DOCKET_INSTALLER_VERSION": "v1.2.3"}), \
             mock.patch.object(self.bootstrap.urllib.request, "urlopen", side_effect=[
                 io.BytesIO((digest + "  docket-installer-darwin-arm64\n").encode()),
                 io.BytesIO(payload),
             ]) as get, mock.patch.object(self.bootstrap.subprocess, "call", return_value=0):
            self.bootstrap.launch([], script=Path("/tmp/install.py"), platform="darwin", machine="arm64")
        self.assertTrue(get.call_args_list[0].args[0].endswith("/releases/download/v1.2.3/SHA256SUMS"))

    def test_checksum_mismatch_refuses_execution(self):
        with mock.patch.object(self.bootstrap.urllib.request, "urlopen", side_effect=[
                 io.BytesIO(("0" * 64 + "  docket-installer-linux-amd64\n").encode()),
                 io.BytesIO(b"tampered"),
             ]), mock.patch.object(self.bootstrap.subprocess, "call") as run:
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                self.bootstrap.launch([], script=Path("/tmp/install.py"), platform="linux", machine="amd64")
        run.assert_not_called()

    def test_missing_release_asset_has_actionable_error(self):
        with mock.patch.object(self.bootstrap.urllib.request, "urlopen", side_effect=OSError("not found")):
            with self.assertRaisesRegex(RuntimeError, "No prebuilt installer is available"):
                self.bootstrap.launch([], script=Path("/tmp/install.py"), platform="linux", machine="amd64")

    def test_local_checkout_builds_and_passes_checkout_and_original_args(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "installer").mkdir()
            (repo / "installer" / "go.mod").write_text("module example\n")
            (repo / "installer" / "install.py").write_text("")
            (repo / "bin").mkdir()
            (repo / "bin" / "docket").write_text("")
            events = []
            with mock.patch.object(self.bootstrap.shutil, "which", return_value="/usr/bin/go"), \
                 mock.patch.object(self.bootstrap.subprocess, "check_call", side_effect=lambda cmd, cwd=None, env=None: events.append(("build", cmd, cwd, env))), \
                 mock.patch.object(self.bootstrap.subprocess, "call", side_effect=lambda cmd, cwd=None: events.append(("run", cmd, cwd)) or 0):
                rc = self.bootstrap.launch(["--dry-run", "--harness", "codex"],
                    script=repo / "installer" / "install.py", cwd="/project")
        self.assertEqual(rc, 0)
        self.assertEqual(events[0][1][0:3], ["/usr/bin/go", "build", "-o"])
        self.assertEqual(events[0][2], str(repo / "installer"))
        self.assertEqual(events[0][3]["CGO_ENABLED"], "0")
        self.assertEqual(events[1][1][1:], ["--checkout", str(repo.resolve()), "--dry-run", "--harness", "codex"])
        self.assertEqual(events[1][2], "/project")

    def test_checkout_without_go_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "installer").mkdir()
            (repo / "installer" / "go.mod").write_text("")
            (repo / "installer" / "install.py").write_text("")
            (repo / "bin").mkdir()
            (repo / "bin" / "docket").write_text("")
            with mock.patch.object(self.bootstrap.shutil, "which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "Go is required"):
                    self.bootstrap.launch([], script=repo / "installer" / "install.py")

    def test_main_reports_execution_oserror_without_traceback(self):
        stderr = io.StringIO()
        with mock.patch.object(self.bootstrap, "launch", side_effect=OSError("permission denied")), \
             redirect_stderr(stderr):
            self.assertEqual(self.bootstrap.main(), 1)
        self.assertEqual(stderr.getvalue(), "docket installer: permission denied\n")

    def test_main_maps_keyboard_interrupt_to_shell_interrupt_status(self):
        stderr = io.StringIO()
        with mock.patch.object(self.bootstrap, "launch", side_effect=KeyboardInterrupt), \
             redirect_stderr(stderr):
            self.assertEqual(self.bootstrap.main(), 130)
        self.assertEqual(stderr.getvalue(), "docket installer: interrupted\n")


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = load("docket_release", HERE / "release.py")

    def test_builds_six_static_binaries_and_checksum_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)

            def fake_check_call(cmd, cwd=None, env=None):
                target = Path(cmd[cmd.index("-o") + 1])
                target.write_bytes(target.name.encode())

            with mock.patch.object(self.release.subprocess, "check_call", side_effect=fake_check_call) as build:
                artifacts = self.release.build_all(output, "1.2.3", installer_dir=HERE)
            self.assertEqual(build.call_count, 6)
            for call in build.call_args_list:
                self.assertEqual(call.kwargs["env"]["CGO_ENABLED"], "0")
                self.assertIn("-X main.version=1.2.3", call.args[0][call.args[0].index("-ldflags") + 1])
            self.assertEqual(len(artifacts), 6)
            lines = (output / "SHA256SUMS").read_text().splitlines()
            self.assertEqual(len(lines), 6)
            self.assertTrue(any(line.endswith("  docket-installer-windows-arm64.exe") for line in lines))


class GraphReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = load("docket_graph_release", HERE.parent / "graph" / "release.py")

    def test_builds_six_viewer_assets_with_graph_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)

            def fake_check_call(cmd, cwd=None, env=None):
                target = Path(cmd[cmd.index("-o") + 1])
                target.write_bytes(target.name.encode())

            with mock.patch.object(self.release.subprocess, "check_call", side_effect=fake_check_call) as build:
                artifacts = self.release.build_all(output, "v1.2.3", graph_dir=HERE.parent / "graph")
            self.assertEqual(build.call_count, 6)
            for call in build.call_args_list:
                self.assertEqual(call.kwargs["env"]["CGO_ENABLED"], "0")
                flags = call.args[0][call.args[0].index("-ldflags") + 1]
                self.assertIn("-X main.version=v1.2.3", flags)
            self.assertEqual(len(artifacts), 6)
            lines = (output / "GRAPH-SHA256SUMS").read_text().splitlines()
            self.assertEqual(len(lines), 6)
            self.assertTrue(any(line.endswith("  docket-graph-windows-arm64.exe") for line in lines))


if __name__ == "__main__":
    unittest.main()
