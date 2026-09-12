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


class AutoScopeTests(unittest.TestCase):
    def _repo(self, home):
        for command in (["git", "init", "-q"],
                        ["git", "config", "user.email", "t@example.com"],
                        ["git", "config", "user.name", "t"]):
            subprocess.run(command, cwd=home, check=True)
        (Path(home) / "tracked.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=home, check=True)
        subprocess.run(["git", "commit", "-qm", "first"], cwd=home, check=True)

    def test_auto_scope_shares_one_base_from_a_subdirectory(self):
        with tempfile.TemporaryDirectory() as home:
            self._repo(home)
            (Path(home) / "tracked.py").write_text("x = 2\n", encoding="utf-8")
            (Path(home) / "new file.py").write_text("y = 1\n", encoding="utf-8")
            nested = Path(home) / "sub"
            nested.mkdir()
            (nested / "deep.py").write_text("z = 1\n", encoding="utf-8")
            cwd = os.getcwd()
            os.chdir(nested)
            try:
                paths = docket_cli.auto_scope_files()
            finally:
                os.chdir(cwd)
        # git diff prints root-relative paths and ls-files --others prints
        # cwd-relative ones, so every path must share the repository root.
        self.assertIn("tracked.py", paths)
        self.assertIn("new file.py", paths)
        self.assertIn("sub/deep.py", paths)

    def test_auto_scope_reports_untracked_files_before_the_first_commit(self):
        with tempfile.TemporaryDirectory() as home:
            subprocess.run(["git", "init", "-q"], cwd=home, check=True)
            (Path(home) / "new.py").write_text("x = 1\n", encoding="utf-8")
            cwd = os.getcwd()
            os.chdir(home)
            try:
                paths = docket_cli.auto_scope_files()
            finally:
                os.chdir(cwd)
        # There is no HEAD yet, so git diff fails. ls-files still knows.
        self.assertEqual(paths, ("new.py",))

    def test_max_chars_is_checked_against_the_configured_minimum(self):
        with tempfile.TemporaryDirectory() as home:
            run(home, "init")
            run(home, "claim", "A premise", "--state", "accepted")
            config = Path(home) / ".docket" / "config.toml"
            config.write_text("[budget]\nminimum = 2000\n", encoding="utf-8")
            rejected = run(home, "context", "--max-chars", "900")
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("at least 2000", rejected.stderr)

    def test_auto_scope_is_empty_outside_a_repository(self):
        with tempfile.TemporaryDirectory() as plain:
            cwd = os.getcwd()
            os.chdir(plain)
            try:
                self.assertEqual(docket_cli.auto_scope_files(), ())
            finally:
                os.chdir(cwd)

    def test_auto_scope_caps_the_path_list(self):
        with tempfile.TemporaryDirectory() as home:
            self._repo(home)
            for index in range(6):
                (Path(home) / f"f{index}.py").write_text("x\n", encoding="utf-8")
            cwd = os.getcwd()
            os.chdir(home)
            try:
                self.assertEqual(len(docket_cli.auto_scope_files(limit=3)), 3)
            finally:
                os.chdir(cwd)

    def test_no_auto_scope_leaves_the_briefing_unscoped(self):
        with tempfile.TemporaryDirectory() as home:
            self._repo(home)
            (Path(home) / "tracked.py").write_text("x = 3\n", encoding="utf-8")
            run(home, "claim", "A premise", "--scope", "tracked.py")
            self.assertNotIn("# files:", run(home, "context", "--no-auto-scope").stdout)
            self.assertIn("# files:", run(home, "context").stdout)

    def test_auto_scope_unions_git_paths_with_an_explicit_file(self):
        with tempfile.TemporaryDirectory() as home:
            self._repo(home)
            (Path(home) / "tracked.py").write_text("x = 3\n", encoding="utf-8")
            run(home, "claim", "A premise", "--scope", "tracked.py")
            out = run(home, "context", "--auto-scope", "--file", "lib/given.py").stdout
            self.assertIn("lib/given.py", out)
            self.assertIn("tracked.py", out)


class InitTests(unittest.TestCase):
    def test_init_ignores_the_lock_file(self):
        with tempfile.TemporaryDirectory() as home:
            run(home, "init")
            ignore = Path(home) / ".docket" / ".gitignore"
            self.assertTrue(ignore.is_file())
            self.assertIn("*.lock", ignore.read_text(encoding="utf-8"))

    def test_init_leaves_an_existing_ignore_file_alone(self):
        with tempfile.TemporaryDirectory() as home:
            ignore = Path(home) / ".docket" / ".gitignore"
            ignore.parent.mkdir(parents=True, exist_ok=True)
            ignore.write_text("# mine\n", encoding="utf-8")
            run(home, "init")
            self.assertEqual(ignore.read_text(encoding="utf-8"), "# mine\n")


class CheckTests(unittest.TestCase):
    def test_check_passes_on_a_good_ledger(self):
        with tempfile.TemporaryDirectory() as home:
            run(home, "claim", "A premise", "--state", "accepted")
            result = run(home, "check")
        self.assertEqual(result.returncode, 0)
        self.assertIn("1 record", result.stdout)

    def test_check_reports_every_duplicate_and_ordering_fault(self):
        with tempfile.TemporaryDirectory() as home:
            ledger = Path(home) / ".docket" / "ledger.jsonl"
            ledger.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                docket_cli.make_record("claim", "First", state="accepted",
                                       author="t", record_id="c1"),
                docket_cli.make_record("claim", "Branch A", state="accepted",
                                       author="t", record_id="c2"),
                docket_cli.make_record("claim", "Branch B", state="accepted",
                                       author="t", record_id="c2"),
                docket_cli.make_record("claim", "Older", state="accepted",
                                       author="t", record_id="c1"),
            ]
            ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            result = run(home, "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate id c2", result.stdout)
        self.assertIn("line 3", result.stdout)
        self.assertIn("line 4", result.stdout)
        self.assertIn("docket rebase", result.stdout)


class RebaseCommandTests(unittest.TestCase):
    def test_rebase_appends_a_renumbered_tail(self):
        with tempfile.TemporaryDirectory() as home:
            # Without init the ledger lives under DOCKET_HOME
            # (tests/test_docket.py:22, bin/docket:160), so .docket/ledger.jsonl
            # does not exist and read_text() raises.
            run(home, "init")
            run(home, "claim", "Shared premise", "--state", "accepted")
            other = Path(home) / "other.jsonl"
            mine = (Path(home) / ".docket" / "ledger.jsonl").read_text()
            theirs = docket_cli.make_record("claim", "Their premise",
                                            state="accepted", author="t",
                                            record_id="c2")
            other.write_text(mine + json.dumps(theirs) + "\n")
            run(home, "claim", "My premise", "--state", "accepted")
            preview = run(home, "rebase", str(other), "--dry-run")
            self.assertIn("c2 -> c3", preview.stdout)
            before = (Path(home) / ".docket" / "ledger.jsonl").read_text()
            self.assertNotIn("Their premise", before)
            result = run(home, "rebase", str(other))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(run(home, "check").returncode, 0)
            after = (Path(home) / ".docket" / "ledger.jsonl").read_text()
        self.assertIn("Their premise", after)


if __name__ == "__main__":
    unittest.main()
