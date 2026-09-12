"""CLI checks. Run directly with ``python3 tests/test_docket.py``."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

DOCKET = str(Path(__file__).resolve().parent.parent / "bin" / "docket")
loader = SourceFileLoader("docket_cli", DOCKET)
spec = importlib.util.spec_from_loader("docket_cli", loader)
docket_cli = importlib.util.module_from_spec(spec)
loader.exec_module(docket_cli)


def run(cwd, *args):
    env = dict(os.environ)
    env["DOCKET_HOME"] = str(Path(cwd) / "global")
    env["DOCKET_AUTHOR"] = "test"
    return subprocess.run([sys.executable, DOCKET, *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


class _TTYBuffer:
    def __init__(self, tty=True):
        self.value = ""
        self.tty = tty

    def isatty(self):
        return self.tty

    def write(self, value):
        self.value += value

    def getvalue(self):
        return self.value

    def flush(self):
        pass

    @property
    def encoding(self):
        return "utf-8"


class CliTests(unittest.TestCase):
    def test_typed_commands_and_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            result = run(root, "question", "Which database?")
            self.assertEqual(result.returncode, 0, result.stderr)
            result = run(root, "claim", "Postgres is supported", "--state", "accepted")
            self.assertIn("c2", result.stdout)
            result = run(root, "decision", "Database", "--choice", "Postgres",
                         "--alternative", "SQLite", "--depends-on", "c2",
                         "--decided-by", "human", "--pin")
            self.assertIn("d3", result.stdout)
            result = run(root, "list", "--kind", "decision", "--json")
            data = json.loads(result.stdout)
            self.assertEqual(len(data), 1)
            self.assertTrue(data[0]["applicable"])
            self.assertEqual(data[0]["decided_by"], "human")

    def test_unknown_refs_and_old_schema_fail_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            result = run(root, "claim", "bad", "--supports", "c99")
            self.assertEqual(result.returncode, 1)
            self.assertIn("unknown or later", result.stderr)
            ledger = root / ".docket" / "ledger.jsonl"
            ledger.parent.mkdir()
            ledger.write_text(json.dumps({"schema": 1}) + "\n")
            result = run(root, "list")
            self.assertEqual(result.returncode, 1)
            self.assertIn("migrate", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_symlinked_cli_resolves_lib_from_real_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            link = root / "docket"
            link.symlink_to(DOCKET)
            result = subprocess.run([str(link), "--version"], cwd=root,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.startswith("docket "))


class GraphDispatchTests(unittest.TestCase):
    def test_graph_dispatch_preserves_terminal_modes_and_cleans_temp_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.jsonl"
            entries = [
                docket_cli.make_record("claim", "Root", state="accepted", author="test", record_id="c1"),
                docket_cli.make_record("decision", "Child", choice="yes", supports=[["c1"]], author="test", record_id="d2"),
                docket_cli.make_record("question", "Open", author="test", record_id="q3"),
            ]
            ledger.write_text("\n".join(json.dumps(item) for item in entries) + "\n")
            originals = (docket_cli.ledger_path, docket_cli.sys.stdin, docket_cli.sys.stdout,
                         docket_cli.sys.stderr, docket_cli._graph_viewer_path,
                         docket_cli.subprocess.run)
            try:
                docket_cli.ledger_path = lambda: ledger
                docket_cli.sys.stdin = _TTYBuffer(True)
                docket_cli.sys.stdout = _TTYBuffer(True)
                docket_cli.sys.stderr = _TTYBuffer(False)
                viewer = root / "viewer"
                viewer.write_text("viewer")
                docket_cli._graph_viewer_path = lambda: viewer
                seen = {}

                def fake_run(argv, **kwargs):
                    seen["argv"] = argv
                    seen["payload"] = json.loads(Path(argv[2]).read_text())
                    self.assertTrue(Path(argv[2]).exists())
                    return subprocess.CompletedProcess(argv, 7)

                docket_cli.subprocess.run = fake_run
                args = type("Args", (), {"style": None, "state": None, "kind": None,
                                          "find": None, "plain": False, "pretty": False,
                                          "interactive": False, "no_interactive": False})()
                self.assertEqual(docket_cli.cmd_graph(args), 7)
                self.assertEqual(seen["payload"]["version"], 2)
                self.assertFalse(Path(seen["argv"][2]).exists())

                pretty = type("Args", (), {"style": None, "state": None, "kind": None,
                                            "find": None, "plain": False, "pretty": True,
                                            "interactive": False, "no_interactive": False})()
                self.assertEqual(docket_cli.cmd_graph(pretty), 7)
                self.assertEqual(seen["argv"][3], "--pretty")

                def broken_run(*argv, **kwargs):
                    seen["broken"] = argv[0][2]
                    raise OSError("Exec format error")

                docket_cli.subprocess.run = broken_run
                self.assertEqual(docket_cli.cmd_graph(args), 1)
                self.assertIn("could not start interactive viewer", docket_cli.sys.stderr.getvalue())
                self.assertFalse(Path(seen["broken"]).exists())

                docket_cli.sys.stdin = _TTYBuffer(False)
                docket_cli.sys.stdout = _TTYBuffer(False)
                called = []
                docket_cli.subprocess.run = lambda *a, **k: called.append((a, k))
                self.assertEqual(docket_cli.cmd_graph(args), 0)
                self.assertFalse(called)
                self.assertIn("Root", docket_cli.sys.stdout.getvalue())

                docket_cli.sys.stdin = _TTYBuffer(True)
                docket_cli.sys.stdout = _TTYBuffer(True)
                docket_cli.sys.stderr = _TTYBuffer(False)
                docket_cli._graph_viewer_path = lambda: root / "missing"
                self.assertEqual(docket_cli.cmd_graph(args), 0)
                self.assertIn("Root", docket_cli.sys.stdout.getvalue())
                self.assertIn("build", docket_cli.sys.stderr.getvalue().lower())

                interactive = type("Args", (), {"style": None, "state": None, "kind": None,
                                                 "find": None, "plain": False, "pretty": False,
                                                 "interactive": True, "no_interactive": False})()
                self.assertEqual(docket_cli.cmd_graph(interactive), 1)
                docket_cli.sys.stdin = _TTYBuffer(False)
                self.assertEqual(docket_cli.cmd_graph(interactive), 1)
                docket_cli.sys.stdin = _TTYBuffer(True)
                docket_cli._graph_viewer_path = lambda: viewer

                def interrupt(*args, **kwargs):
                    seen["interrupt"] = args[0][2]
                    raise KeyboardInterrupt

                docket_cli.subprocess.run = interrupt
                self.assertEqual(docket_cli.cmd_graph(interactive), 130)
                self.assertFalse(Path(seen["interrupt"]).exists())
            finally:
                (docket_cli.ledger_path, docket_cli.sys.stdin, docket_cli.sys.stdout,
                 docket_cli.sys.stderr, docket_cli._graph_viewer_path,
                 docket_cli.subprocess.run) = originals

    def test_graph_flag_conflicts(self):
        for flags in (("--interactive", "--no-interactive"),
                      ("--interactive", "--plain"),
                      ("--interactive", "--style", "rail")):
            result = subprocess.run([sys.executable, DOCKET, "graph", *flags],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)

    def test_top_level_help_and_invalid_command(self):
        release = (Path(DOCKET).parent.parent / "VERSION").read_text().strip()
        for flags in ((), ("-h",), ("--help",)):
            result = subprocess.run([sys.executable, DOCKET, *flags], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.startswith(f"docket {release}\n"))
            self.assertIn("usage: docket", result.stdout)
            self.assertIn("claim", result.stdout)
            self.assertIn("graph", result.stdout)
            self.assertNotIn("SessionStart hook", result.stdout)
            self.assertEqual(result.stderr, "")
        result = subprocess.run([sys.executable, DOCKET, "not-a-command"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_graph_payload_is_version_two_and_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / ".docket" / "ledger.jsonl"
            ledger.parent.mkdir()
            env = dict(os.environ, DOCKET_HOME=str(root / "global"), DOCKET_AUTHOR="test")
            subprocess.run([sys.executable, DOCKET, "claim", "Premise", "--state", "accepted"],
                           cwd=root, env=env, check=True, capture_output=True, text=True)
            subprocess.run([sys.executable, DOCKET, "decision", "Choice", "--choice", "yes",
                           "--depends-on", "c1"], cwd=root, env=env, check=True,
                           capture_output=True, text=True)
            result = run(root, "init")
            self.assertEqual(result.returncode, 0, result.stderr)
            entries = docket_cli.read(ledger)
            payload = docket_cli._graph_payload(entries, docket_cli.retired_by(entries))
            self.assertEqual(payload["version"], 2)
            by_id = {entry["id"]: entry for entry in payload["entries"]}
            self.assertEqual(by_id["d2"]["kind"], "decision")
            self.assertTrue(by_id["d2"]["applicable"])
            self.assertEqual(by_id["d2"]["depends_on"], ["c1"])

    def test_static_graph_shows_blocked_decision_prerequisites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.jsonl"
            entries = [
                docket_cli.make_record("claim", "Unassessed", author="test", record_id="c1"),
                docket_cli.make_record("decision", "Blocked choice", choice="yes",
                                       depends_on=["c1"], author="test", record_id="d2"),
            ]
            ledger.write_text("\n".join(json.dumps(item) for item in entries) + "\n")
            original = docket_cli.ledger_path
            old_stdout = docket_cli.sys.stdout
            try:
                docket_cli.ledger_path = lambda: ledger
                docket_cli.sys.stdout = _TTYBuffer(False)
                args = type("Args", (), {"style": "compact", "state": None, "kind": None,
                                          "find": None, "plain": True, "pretty": False,
                                          "interactive": False, "no_interactive": False})()
                self.assertEqual(docket_cli.cmd_graph(args), 0)
                self.assertIn("blocked by c1", docket_cli.sys.stdout.getvalue())
            finally:
                docket_cli.ledger_path = original
                docket_cli.sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
