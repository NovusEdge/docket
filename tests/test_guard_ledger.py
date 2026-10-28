import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Someone running with the hooks off must still get the default behavior under test.
os.environ.pop("DOCKET_HOOKS", None)

GUARD = Path(__file__).parent.parent / "hooks" / "guard_ledger.py"
CWD = "/home/user/project"
# Every variable the hook reads a session id from; a test run inside Claude
# Code inherits CLAUDE_CODE_BRIDGE_SESSION_ID.
SESSION_VARS = ("CLAUDE_SESSION_ID", "CLAUDE_CODE_BRIDGE_SESSION_ID", "SESSION_ID")


def decide(tool, tool_input, cwd=CWD, env=None):
    payload = json.dumps(
        {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": cwd}
    )
    result = subprocess.run(
        [sys.executable, str(GUARD)], input=payload, capture_output=True, text=True, env=env
    )
    if not result.stdout.strip():
        return "allow"
    return json.loads(result.stdout)["hookSpecificOutput"].get("permissionDecision", "allow")


def bash(command):
    return decide("Bash", {"command": command})


class LedgerPathTests(unittest.TestCase):
    def test_edit_and_write_on_a_ledger_ask(self):
        for tool in ("Edit", "Write", "MultiEdit"):
            for path in (
                ".docket/ledger.jsonl",
                "/home/user/project/.docket/ledger.jsonl",
                ".docket/ledger.jsonl.schema1",
                ".docket/ledger.jsonl.schema2",
                ".docket/migration-v0.8-map.json",
            ):
                with self.subTest(tool=tool, path=path):
                    self.assertEqual(decide(tool, {"file_path": path}), "ask")

    def test_every_schema_backup_asks(self):
        for path in (
            ".docket/ledger.jsonl.schema1",
            ".docket/ledger.jsonl.schema2",
            ".docket/ledger.jsonl.schema12",
            ".docket/features.jsonl.schema1",
        ):
            with self.subTest(path=path):
                self.assertEqual(decide("Edit", {"file_path": path}), "ask")

    def test_a_name_that_only_looks_like_a_backup_is_untouched(self):
        for path in (".docket/ledger.jsonl.schema", ".docket/ledger.jsonl.schemax"):
            with self.subTest(path=path):
                self.assertEqual(decide("Edit", {"file_path": path}), "allow")

    def test_an_ordinary_file_is_untouched(self):
        for path in ("docket/ledger.py", "README.md", "docket/notes.jsonl", ".docket/notes.txt"):
            with self.subTest(path=path):
                self.assertEqual(decide("Edit", {"file_path": path}), "allow")

    def test_a_global_ledger_asks(self):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CONFIG_DIR", "DOCKET_HOME")}
        path = Path.home() / ".claude/docket/x/ledger.jsonl"
        self.assertEqual(decide("Write", {"file_path": str(path)}, env=env), "ask")

    def test_a_global_ledger_under_claude_config_dir_asks(self):
        env = {k: v for k, v in os.environ.items() if k != "DOCKET_HOME"}
        env["CLAUDE_CONFIG_DIR"] = "/home/user/.claude-work"
        path = "/home/user/.claude-work/docket/x/ledger.jsonl"
        self.assertEqual(decide("Write", {"file_path": path}, env=env), "ask")


class BashTests(unittest.TestCase):
    def test_the_cli_passes(self):
        for command in (
            "docket context",
            "./bin/docket decision 'Which cache?' --choice redis",
            "python3 bin/docket check",
            "DOCKET_AUTHOR=me docket claim 'A premise'",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "allow")

    def test_reading_a_ledger_passes(self):
        for command in (
            "cat .docket/ledger.jsonl",
            "wc -l .docket/ledger.jsonl",
            "grep decision .docket/ledger.jsonl | head -3",
            "jq -r .id .docket/ledger.jsonl",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "allow")

    def test_writing_a_ledger_asks(self):
        for command in (
            "echo '{}' >> .docket/ledger.jsonl",
            "sed -i 's/a/b/' .docket/ledger.jsonl",
            "rm .docket/ledger.jsonl",
            "cp /tmp/x.jsonl .docket/ledger.jsonl",
            "mv .docket/ledger.jsonl /tmp/",
            "truncate -s 0 .docket/ledger.jsonl",
            "tee .docket/ledger.jsonl < /tmp/x",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "ask")

    def test_a_reader_in_its_write_mode_asks(self):
        for command in (
            "git checkout HEAD~3 -- .docket/ledger.jsonl",
            "git restore .docket/ledger.jsonl",
            "git -C /home/user/project checkout main -- .docket/ledger.jsonl",
            "git reset --hard -- .docket/ledger.jsonl",
            "find .docket -name 'ledger.jsonl' -delete",
            "find .docket -name 'ledger.jsonl' -exec rm {} +",
            "sort -o .docket/ledger.jsonl .docket/ledger.jsonl",
            "sort -uo .docket/ledger.jsonl /tmp/x",
            "sort --output=.docket/ledger.jsonl /tmp/x",
            "sort --output .docket/ledger.jsonl /tmp/x",
            "uniq /tmp/x .docket/ledger.jsonl",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "ask")

    def test_the_same_readers_still_pass_when_they_only_read(self):
        for command in (
            "git log --oneline -- .docket/ledger.jsonl",
            "git show HEAD:.docket/ledger.jsonl",
            "git diff .docket/ledger.jsonl",
            "git -C /home/user/project log -1 .docket/ledger.jsonl",
            "find .docket -name 'ledger.jsonl'",
            "sort .docket/ledger.jsonl",
            "uniq .docket/ledger.jsonl",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "allow")

    def test_committing_a_ledger_passes(self):
        for command in (
            "git add .docket/ledger.jsonl",
            "git add .docket/",
            "git stage .docket/ledger.jsonl",
            "git commit -m 'record decisions' .docket/ledger.jsonl",
            "docket check && git add .docket/ledger.jsonl && git commit -m 'record decisions'",
            "git add .docket/ledger.jsonl docs/a.md && git commit -s -F - <<'EOF'\n"
            "formalism: mention `docket` and $(x) in .docket/ledger.jsonl\nEOF",
            "git add .docket/ledger.jsonl && git commit -m \"$(cat <<'EOF'\n"
            'msg with `ticks` > and .docket/ledger.jsonl\nEOF\n)"',
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "allow")

    def test_a_commit_message_cannot_hide_a_write(self):
        for command in (
            # An unquoted delimiter expands the body, so the substitution runs.
            "git commit -F - <<EOF\n$(rm .docket/ledger.jsonl)\nEOF",
            "git commit -F - <<'EOF'\nmsg\nEOF\nrm .docket/ledger.jsonl",
            "git add .docket/ledger.jsonl && python3 - <<'PY'\nopen('.docket/ledger.jsonl','a')\nPY",
            "cat <<'EOF' > .docket/ledger.jsonl\n{}\nEOF",
            "git rm .docket/ledger.jsonl",
            "git checkout main -- . && cat .docket/ledger.jsonl",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "ask")

    def test_an_opaque_command_naming_a_ledger_asks(self):
        # None of these say what they do, which is the point of asking.
        for command in (
            "python3 -c \"open('.docket/ledger.jsonl','a').write('x')\"",
            "python3 - .docket/ledger.jsonl <<'PY'\nprint(1)\nPY",
            "perl -e 'unlink \".docket/ledger.jsonl\"'",
            'node -e \'require("fs").writeFileSync(".docket/ledger.jsonl","")\'',
            'eval "cat .docket/ledger.jsonl"',
            "echo $(cat .docket/ledger.jsonl)",
            "base64 -d < x | tee .docket/ledger.jsonl",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "ask")

    def test_a_cd_prefix_moves_later_relative_paths(self):
        for command in (
            "cd .docket && sed -i s/x/y/ ledger.jsonl",
            "cd .docket; rm ledger.jsonl",
            "cd /home/user/project && cd .docket && echo x >> ledger.jsonl",
            "cd '.docket' && rm ledger.jsonl",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "ask")
        for command in ("cd .docket && cat ledger.jsonl", "cd src && rm ledger.jsonl"):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "allow")

    def test_a_glob_under_docket_may_be_the_ledger(self):
        for command in (
            "echo x >> .docket/l*",
            "rm .docket/*.jsonl",
            "truncate -s 0 .docket/led?er.jsonl",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "ask")
        self.assertEqual(bash("rm .docket/*.md"), "allow")
        self.assertEqual(bash("rm src/l*"), "allow")

    def test_redirects_that_write_nothing_do_not_ask(self):
        for command in (
            "grep x .docket/ledger.jsonl 2>/dev/null",
            "grep x .docket/ledger.jsonl > /dev/null 2>&1",
            "cat .docket/ledger.jsonl &>/dev/null",
            "grep x .docket/ledger.jsonl 2>&1 | head",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "allow")
        for command in (
            "grep x .docket/ledger.jsonl > .docket/ledger.jsonl",
            "cat /tmp/x 2>/dev/null >> .docket/ledger.jsonl",
        ):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "ask")

    def test_a_command_naming_no_ledger_passes(self):
        for command in ("python3 -c \"open('notes.txt','w')\"", "rm -rf build/", "git status"):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "allow")


DOCKET = Path(__file__).parent.parent / "bin" / "docket"


class GoverningRecordTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.project = base / "project"
        (self.project / ".git").mkdir(parents=True)
        (self.project / ".docket").mkdir()
        self.env = {
            **os.environ,
            "XDG_STATE_HOME": str(base / "state"),
            "DOCKET_HOME": str(base / "home"),
            "DOCKET_AUTHOR": "tester",
            "CLAUDE_SESSION_ID": "sess-1",
        }
        self.state = base / "state"

    def record(self, text, *scopes, extra=()):
        command = [sys.executable, str(DOCKET), "decision", text, "--choice", "c", "--json"]
        for scope in scopes:
            command += ["--scope", scope]
        done = subprocess.run(
            [*command, *extra], cwd=self.project, env=self.env, capture_output=True, text=True
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["id"]

    def run_hook(self, path, tool="Edit", env=None, session=None):
        body = {"tool_name": tool, "tool_input": {"file_path": path}, "cwd": str(self.project)}
        if session:
            body["session_id"] = session
        payload = json.dumps(body)
        done = subprocess.run(
            [sys.executable, str(GUARD)],
            input=payload,
            capture_output=True,
            text=True,
            env=env or self.env,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["hookSpecificOutput"] if done.stdout.strip() else None

    def test_an_exact_scope_surfaces_without_deciding_permission(self):
        ident = self.record("Cache in redis", "src/cache.py")
        out = self.run_hook("src/cache.py")
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", out)
        self.assertIn(f"{ident} decision adopted", out["additionalContext"])
        self.assertIn("Cache in redis", out["additionalContext"])
        self.assertIn("docket show", out["additionalContext"])

    def test_an_absolute_path_matches_the_relative_scope(self):
        self.record("Cache in redis", "src/cache.py")
        self.assertIsNotNone(self.run_hook(str(self.project / "src" / "cache.py")))

    def test_a_narrow_directory_scope_covers_its_files(self):
        self.record("Web only", "docket/web/**")
        self.record("Slash form", "docket/construct/")
        self.assertIsNotNone(self.run_hook("docket/web/app/x.py"))
        self.assertIsNotNone(self.run_hook("docket/construct/run.py"))

    def test_a_top_level_directory_scope_is_package_wide_and_stays_quiet(self):
        self.record("Everything in docs", "docs/**")
        self.record("Everything in hooks", "hooks/")
        self.assertIsNone(self.run_hook("docs/a.md"))
        self.assertIsNone(self.run_hook("hooks/x.py"))

    def test_a_glob_or_unrelated_path_stays_quiet(self):
        self.record("Any python", "src/*.py")
        self.record("Other file", "src/other.py")
        self.assertIsNone(self.run_hook("src/cache.py"))

    def test_a_retired_record_is_left_out(self):
        old = self.record("Old", "src/cache.py")
        new = self.record(
            "New", "src/cache.py", extra=("--supersedes", old, "--supersede-reason", "revise")
        )
        context = self.run_hook("src/cache.py")["additionalContext"]
        self.assertIn(new, context)
        self.assertNotIn(f"{old} ", context)

    def test_the_list_is_capped_and_says_so(self):
        for n in range(11):
            self.record(f"Rule {n}", "src/cache.py")
        context = self.run_hook("src/cache.py")["additionalContext"]
        self.assertLessEqual(len(context.splitlines()), 10)
        self.assertIn("more", context)

    def test_a_long_headline_is_clipped(self):
        self.record("x" * 400, "src/cache.py")
        self.assertLess(len(self.run_hook("src/cache.py")["additionalContext"]), 400)

    def test_a_file_surfaces_once_per_session(self):
        self.record("Cache in redis", "src/cache.py")
        self.assertIsNotNone(self.run_hook("src/cache.py"))
        self.assertIsNone(self.run_hook("src/cache.py"))
        self.assertIsNone(self.run_hook(str(self.project / "src" / "cache.py")))
        other = {**self.env, "CLAUDE_SESSION_ID": "sess-2"}
        self.assertIsNotNone(self.run_hook("src/cache.py", env=other))

    def test_state_lives_outside_the_repository(self):
        self.record("Cache in redis", "src/cache.py")
        self.run_hook("src/cache.py")
        self.assertTrue(any(self.state.rglob("*sess-1*")))
        self.assertFalse(any(p.name.startswith("sess") for p in self.project.rglob("*")))

    def test_the_payload_session_id_dedupes_without_an_environment_variable(self):
        self.record("Cache in redis", "src/cache.py")
        env = {k: v for k, v in self.env.items() if k not in SESSION_VARS}
        self.assertIsNotNone(self.run_hook("src/cache.py", env=env, session="from-payload"))
        self.assertIsNone(self.run_hook("src/cache.py", env=env, session="from-payload"))

    def test_without_a_session_every_edit_surfaces(self):
        self.record("Cache in redis", "src/cache.py")
        env = {k: v for k, v in self.env.items() if k not in SESSION_VARS}
        self.assertIsNotNone(self.run_hook("src/cache.py", env=env))
        self.assertIsNotNone(self.run_hook("src/cache.py", env=env))

    def test_a_broken_ledger_fails_open(self):
        (self.project / ".docket" / "ledger.jsonl").write_text("{not json\n")
        self.assertIsNone(self.run_hook("src/cache.py"))

    def test_a_ledger_edit_asks_and_tells_the_agent_what_to_run_instead(self):
        out = self.run_hook(".docket/ledger.jsonl")
        self.assertEqual(out["permissionDecision"], "ask")
        for word in ("docket correct", "docket record", "--supersedes"):
            self.assertIn(word, out["additionalContext"])

    def test_bash_gets_no_record_context(self):
        self.record("Cache in redis", "src/cache.py")
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "ls src/cache.py"},
                "cwd": str(self.project),
            }
        )
        done = subprocess.run(
            [sys.executable, str(GUARD)],
            input=payload,
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(done.stdout.strip(), "")


class FeatureNudgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.project = base / "project"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.project)], check=True)
        (self.project / ".docket").mkdir()
        (self.project / ".docket" / "ledger.jsonl").write_text("", encoding="utf-8")
        self.env = {
            **os.environ,
            "XDG_STATE_HOME": str(base / "state"),
            "DOCKET_HOME": str(base / "home"),
            "DOCKET_AUTHOR": "tester",
            "CLAUDE_SESSION_ID": "sess-1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.test",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.test",
        }

    def edit(self, path, env=None):
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": path}, "cwd": str(self.project)}
        )
        done = subprocess.run(
            [sys.executable, str(GUARD)],
            input=payload,
            capture_output=True,
            text=True,
            env=env or self.env,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)["hookSpecificOutput"] if done.stdout.strip() else None
        return out["additionalContext"] if out else None

    def test_the_third_distinct_file_gets_the_nudge(self):
        self.assertIsNone(self.edit("a/one.py"))
        self.assertIsNone(self.edit("a/two.py"))
        context = self.edit("b/three.py")
        self.assertIn("feature start", context)
        self.assertIn("docket-feature", context)
        self.assertIn("b/three.py", context)

    def test_editing_one_file_repeatedly_counts_once(self):
        for _ in range(4):
            self.assertIsNone(self.edit("a/one.py"))
        self.assertIsNone(self.edit(str(self.project / "a" / "one.py")))

    def test_the_nudge_fires_once_per_session(self):
        for name in ("one", "two", "three"):
            self.edit(f"a/{name}.py")
        self.assertIsNone(self.edit("a/four.py"))
        other = {**self.env, "CLAUDE_SESSION_ID": "sess-2"}
        for name in ("one", "two"):
            self.assertIsNone(self.edit(f"a/{name}.py", env=other))
        self.assertIsNotNone(self.edit("a/three.py", env=other))

    def test_an_open_feature_silences_it(self):
        started = subprocess.run(
            [sys.executable, str(DOCKET), "feature", "start", "w", "--text", "t", "--path", "a/**"],
            cwd=self.project,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        for name in ("one", "two", "three", "four"):
            self.assertIsNone(self.edit(f"a/{name}.py"))

    def test_a_project_without_a_ledger_gets_no_nudge(self):
        (self.project / ".docket" / "ledger.jsonl").unlink()
        for name in ("one", "two", "three"):
            self.assertIsNone(self.edit(f"a/{name}.py"))

    def test_docket_files_do_not_count(self):
        self.edit("a/one.py")
        self.edit("a/two.py")
        self.assertIsNone(self.edit(".docket/config.toml"))

    def test_without_a_session_there_is_no_nudge(self):
        env = {k: v for k, v in self.env.items() if k not in SESSION_VARS}
        for name in ("one", "two", "three"):
            self.assertIsNone(self.edit(f"a/{name}.py", env=env))

    def test_it_joins_the_governing_records_on_the_same_edit(self):
        recorded = subprocess.run(
            [sys.executable, str(DOCKET), "decision", "Rule", "--choice", "c"]
            + ["--scope", "src/core/x.py"],
            cwd=self.project,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.edit("a/one.py")
        self.edit("a/two.py")
        context = self.edit("src/core/x.py")
        self.assertIn("Recorded decisions govern", context)
        self.assertIn("feature start", context)


class HooksOffTests(unittest.TestCase):
    def test_off_silences_a_ledger_write_and_the_nudge(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                **os.environ,
                "DOCKET_HOOKS": "off",
                "XDG_STATE_HOME": tmp,
                "CLAUDE_SESSION_ID": "s",
            }
            calls = [("Edit", {"file_path": ".docket/ledger.jsonl"})]
            calls += [("Edit", {"file_path": f"a/{n}.py"}) for n in ("one", "two", "three")]
            for tool, tool_input in calls:
                payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": tmp})
                done = subprocess.run(
                    [sys.executable, str(GUARD)],
                    input=payload,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_any_other_value_leaves_the_guard_on(self):
        env = {**os.environ, "DOCKET_HOOKS": "on"}
        self.assertEqual(decide("Edit", {"file_path": ".docket/ledger.jsonl"}, env=env), "ask")


class RobustnessTests(unittest.TestCase):
    def test_malformed_input_allows(self):
        result = subprocess.run(
            [sys.executable, str(GUARD)], input="not json", capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_an_unknown_tool_allows(self):
        self.assertEqual(decide("WebFetch", {"url": "https://example.com"}), "allow")


if __name__ == "__main__":
    unittest.main()
