import json
import subprocess
import sys
import unittest
from pathlib import Path

GUARD = Path(__file__).parent.parent / "hooks" / "guard_ledger.py"
CWD = "/home/user/project"


def decide(tool, tool_input, cwd=CWD):
    payload = json.dumps(
        {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": cwd}
    )
    result = subprocess.run(
        [sys.executable, str(GUARD)], input=payload, capture_output=True, text=True
    )
    if not result.stdout.strip():
        return "allow"
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]


def bash(command):
    return decide("Bash", {"command": command})


class LedgerPathTests(unittest.TestCase):
    def test_edit_and_write_on_a_ledger_ask(self):
        for tool in ("Edit", "Write", "MultiEdit"):
            for path in (
                ".docket/ledger.jsonl",
                "/home/user/project/.docket/ledger.jsonl",
                ".docket/ledger.jsonl.schema1",
                ".docket/migration-v0.8-map.json",
            ):
                with self.subTest(tool=tool, path=path):
                    self.assertEqual(decide(tool, {"file_path": path}), "ask")

    def test_an_ordinary_file_is_untouched(self):
        for path in ("docket/ledger.py", "README.md", "docket/notes.jsonl", ".docket/notes.txt"):
            with self.subTest(path=path):
                self.assertEqual(decide("Edit", {"file_path": path}), "allow")

    def test_a_global_ledger_asks(self):
        self.assertEqual(
            decide("Write", {"file_path": str(Path.home() / ".claude/docket/x/ledger.jsonl")}),
            "ask",
        )


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

    def test_a_command_naming_no_ledger_passes(self):
        for command in ("python3 -c \"open('notes.txt','w')\"", "rm -rf build/", "git status"):
            with self.subTest(command=command):
                self.assertEqual(bash(command), "allow")


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
