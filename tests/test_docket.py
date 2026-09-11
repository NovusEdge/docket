"""Run with: python3 tests/test_docket.py"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

DOCKET = str(Path(__file__).resolve().parent.parent / "bin" / "docket")

# bin/docket has no .py extension, so it needs an explicit loader instead of
# a normal import.
_loader = SourceFileLoader("docket_cli", DOCKET)
_spec = importlib.util.spec_from_loader("docket_cli", _loader)
docket_cli = importlib.util.module_from_spec(_spec)
_loader.exec_module(docket_cli)


def run(cwd, *args, home=None):
    env = dict(os.environ)
    # Point the global store at a temp dir so tests never touch the real one.
    env["DOCKET_HOME"] = str(home) if home else str(Path(cwd) / "_global")
    env.pop("CLAUDE_CONFIG_DIR", None)
    return subprocess.run(
        [sys.executable, DOCKET, *args], cwd=cwd, capture_output=True, text=True, env=env
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        r = run(d, "context")
        assert r.returncode == 0, r.stderr
        assert r.stdout == "", f"empty project must cost no context, got {r.stdout!r}"

        r = run(d, "context", "--for", "gemini")
        assert r.returncode == 0, r.stderr
        assert r.stdout == "", "an empty ledger must print nothing even wrapped for a harness"

        # This block exercises the project-local ledger, so opt into one.
        (d / ".git").mkdir()
        r = run(d, "init")
        assert (d / ".docket" / "ledger.jsonl").exists(), r.stdout

        r = run(d, "add", "Which database?", "--answer", "Postgres", "--cost", "migration")
        assert r.returncode == 0, r.stderr
        assert "d1" in r.stdout

        r = run(d, "add", "Use an ORM?", "--state", "ruled-out", "--answer", "No")
        assert "d2" in r.stdout

        # A justification must name an entry that exists.
        r = run(d, "add", "Driver?", "--answer", "psycopg", "--because", "d99")
        assert r.returncode == 1, "unknown justification id must fail"
        assert "d99" in r.stderr

        r = run(d, "add", "Driver?", "--answer", "psycopg", "--because", "d1")
        assert r.returncode == 0, r.stderr

        r = run(d, "list", "--state", "ruled-out")
        assert "Use an ORM?" in r.stdout
        assert "Which database?" not in r.stdout

        r = run(d, "list", "--find", "postgres")
        assert "Which database?" in r.stdout, "find must be case-insensitive"

        r = run(d, "context")
        assert "Settled" in r.stdout and "Ruled out" in r.stdout
        assert "migration" in r.stdout, "cost_if_wrong belongs in injected context"
        assert r.stdout.startswith("# docket:"), "plain context output must not change"
        assert not r.stdout.lstrip().startswith("{"), "plain context output must not be JSON"

        r = run(d, "context", "--for", "gemini")
        envelope = json.loads(r.stdout)
        ledger_text = envelope["hookSpecificOutput"]["additionalContext"]
        assert envelope["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "Which database?" in ledger_text

        r = run(d, "context", "--for", "copilot")
        envelope = json.loads(r.stdout)
        assert "Which database?" in envelope["additionalContext"]

        r = run(d, "context", "--for", "cursor")
        envelope = json.loads(r.stdout)
        assert "Which database?" in envelope["additional_context"]

        r = run(d, "show", "d3")
        entry = json.loads(r.stdout)
        assert entry["because"] == [["d1"]]
        # Provenance fields are append-only and cannot be backfilled.
        assert entry["author"], "an entry must say who recorded it"
        assert "branch" in entry and "session" in entry

        # A subdirectory shares the project's ledger.
        sub = d / "src" / "deep"
        sub.mkdir(parents=True)
        r = run(sub, "list")
        assert "Which database?" in r.stdout, "ledger lookup must walk up"

        # A legacy flat because (list of strings) still reads as one set.
        ledger = d / ".docket" / "ledger.jsonl"
        legacy = json.dumps({
            "id": "d4", "ts": "2020-01-01T00:00:00+00:00", "state": "settled",
            "question": "Legacy?", "answer": "Yes", "because": ["d1"],
            "cost_if_wrong": "", "session": "", "author": "legacy", "branch": "",
        })
        with ledger.open("a") as f:
            f.write(legacy + "\n")
        r = run(d, "list")
        assert "d1" in r.stdout and "Legacy?" in r.stdout

        # Repeated --because produces two alternative support sets.
        r = run(d, "add", "Alternative supports?", "--answer", "Either works",
                "--because", "d1,d2", "--because", "d1")
        assert r.returncode == 0, r.stderr
        d5 = json.loads(run(d, "show", "d5").stdout)
        assert d5["because"] == [["d1", "d2"], ["d1"]], d5

        # list renders a genuine nested because without crashing.
        r = run(d, "list")
        assert r.returncode == 0, r.stderr
        assert "d1,d2 | d1" in r.stdout

        # An unknown id inside any alternative set still fails validation.
        r = run(d, "add", "Bad alt?", "--answer", "no", "--because", "d1", "--because", "d99")
        assert r.returncode == 1, "unknown id in a later alternative set must fail"
        assert "d99" in r.stderr

        # A mixed-shape because (flat list holding a nested list) degrades
        # instead of crashing list's rendering.
        mixed = json.dumps({
            "id": "dmixed", "ts": "2020-01-01T00:00:00+00:00", "state": "settled",
            "question": "Mixed shape?", "answer": "n/a", "because": ["d1", ["d2", "d3"]],
            "cost_if_wrong": "", "session": "", "author": "x", "branch": "",
        })
        with ledger.open("a") as f:
            f.write(mixed + "\n")
        r = run(d, "list")
        assert r.returncode == 0, r.stderr
        assert "dmixed" in r.stderr

        # because holding a non-string, non-list element degrades the same way.
        bad_elem = json.dumps({
            "id": "dbadelem", "ts": "2020-01-01T00:00:00+00:00", "state": "settled",
            "question": "Bad element?", "answer": "n/a", "because": [1, 2],
            "cost_if_wrong": "", "session": "", "author": "x", "branch": "",
        })
        with ledger.open("a") as f:
            f.write(bad_elem + "\n")
        r = run(d, "list")
        assert r.returncode == 0, r.stderr
        assert "dbadelem" in r.stderr

        # A malformed line is skipped, and the rest still parse.
        with ledger.open("a") as f:
            f.write("not json\n")
        r = run(d, "list")
        assert r.returncode == 0
        assert "Which database?" in r.stdout

    # Without a project .docket, entries go to the global store keyed by project.
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        g = d / "global"
        (d / "proj-a" / "src").mkdir(parents=True)
        (d / "proj-a" / ".git").mkdir()
        (d / "proj-b").mkdir()
        (d / "proj-b" / ".git").mkdir()

        r = run(d / "proj-a", "add", "A question", "--answer", "A", home=g)
        assert r.returncode == 0, r.stderr
        assert not (d / "proj-a" / ".docket").exists(), "must not write into the project"

        r = run(d / "proj-b", "add", "B question", "--answer", "B", home=g)
        assert r.returncode == 0

        # Ledgers stay separate per project.
        r = run(d / "proj-a", "list", home=g)
        assert "A question" in r.stdout and "B question" not in r.stdout

        # A subdirectory resolves to the same project ledger via the git root.
        r = run(d / "proj-a" / "src", "list", home=g)
        assert "A question" in r.stdout, "git root must anchor the global key"

        r = run(d / "proj-a", "where", home=g)
        assert "global" in r.stdout

        # init moves the global ledger into the repository.
        r = run(d / "proj-a", "init", home=g)
        assert "moved 1 entry" in r.stdout, r.stdout
        assert (d / "proj-a" / ".docket" / "ledger.jsonl").exists()
        r = run(d / "proj-a", "list", home=g)
        assert "A question" in r.stdout
        r = run(d / "proj-a", "where", home=g)
        assert "project" in r.stdout

        r = run(d / "proj-a", "init", home=g)
        assert "already project-local" in r.stdout

        # Branch is recorded from the project root, not the working directory.
        subprocess.run(["git", "init", "-q", "-b", "trunk"], cwd=d / "proj-a", check=True)
        r = run(d / "proj-a" / "src", "add", "Branch check", "--answer", "yes", home=g)
        assert r.returncode == 0, r.stderr
        entries = [
            json.loads(line)
            for line in (d / "proj-a" / ".docket" / "ledger.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert entries[-1]["branch"] == "trunk", entries[-1]

        # DOCKET_AUTHOR overrides detection.
        env_author = dict(os.environ)
        env_author["DOCKET_HOME"] = str(g)
        env_author["DOCKET_AUTHOR"] = "codex"
        subprocess.run(
            [sys.executable, DOCKET, "add", "Who wrote this?", "--answer", "codex did"],
            cwd=d / "proj-a", capture_output=True, text=True, env=env_author, check=True,
        )
        last = json.loads(
            (d / "proj-a" / ".docket" / "ledger.jsonl").read_text().splitlines()[-1]
        )
        assert last["author"] == "codex", last

        # No detectable author: entry gets "unknown", a stderr warning, exit 0.
        env_blank = dict(os.environ)
        env_blank["DOCKET_HOME"] = str(g)
        for var in ("DOCKET_AUTHOR", "AI_AGENT", "CODEX_SANDBOX", "CODEX_HOME", "USER"):
            env_blank.pop(var, None)
        r = subprocess.run(
            [sys.executable, DOCKET, "add", "No author?", "--answer", "n/a"],
            cwd=d / "proj-a", capture_output=True, text=True, env=env_blank,
        )
        assert r.returncode == 0, r.stderr
        assert "DOCKET_AUTHOR" in r.stderr
        last = json.loads(
            (d / "proj-a" / ".docket" / "ledger.jsonl").read_text().splitlines()[-1]
        )
        assert last["author"] == "unknown", last

    # A later entry retires an earlier one. The log is append-only, so the
    # retired entry keeps its own state forever and only this link exposes it.
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / ".git").mkdir()
        run(d, "init")
        ledger = d / ".docket" / "ledger.jsonl"

        run(d, "add", "Fix the schema doc", "--state", "open", "--answer", "Not done")
        run(d, "add", "Unrelated", "--answer", "Still current")

        r = run(d, "add", "Was it fixed?", "--answer", "Yes", "--supersedes", "d99")
        assert r.returncode == 1, "superseding an unknown id must fail"
        assert "d99" in r.stderr

        r = run(d, "add", "Was it fixed?", "--answer", "Yes", "--supersedes", "d1")
        assert r.returncode == 0, r.stderr
        assert json.loads(run(d, "show", "d3").stdout)["supersedes"] == ["d1"]

        r = run(d, "list", "--state", "open")
        assert "Fix the schema doc" not in r.stdout, "a retired entry must leave the open list"

        r = run(d, "list")
        assert "Fix the schema doc" not in r.stdout
        assert "Unrelated" in r.stdout, "only the retired entry is hidden"

        r = run(d, "list", "--superseded")
        assert "Fix the schema doc" in r.stdout
        assert "superseded by d3" in r.stdout

        r = run(d, "context")
        assert "Fix the schema doc" not in r.stdout, "injected context must not carry stale state"
        assert "Unrelated" in r.stdout

        # show reaches a retired entry directly; the history stays readable.
        assert json.loads(run(d, "show", "d1").stdout)["question"] == "Fix the schema doc"

        # A malformed supersedes degrades the way a malformed because does.
        bad = json.dumps({
            "id": "dbad", "ts": "2020-01-01T00:00:00+00:00", "state": "settled",
            "question": "Bad supersedes?", "answer": "n/a", "because": [],
            "supersedes": [1], "cost_if_wrong": "", "session": "", "author": "x",
            "branch": "",
        })
        with ledger.open("a") as f:
            f.write(bad + "\n")
        r = run(d, "list")
        assert r.returncode == 0, r.stderr
        assert "dbad" in r.stderr
        assert "Unrelated" in r.stdout, "one bad entry must not hide the rest"

    # The Codex manifest sat at 0.6.0 while the Claude one reached 0.6.3,
    # because nothing compared them.
    root = Path(DOCKET).parent.parent
    release = (root / "VERSION").read_text().strip()
    for manifest in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        declared = json.loads((root / manifest).read_text())["version"]
        assert declared == release, f"{manifest} says {declared}, VERSION says {release}"

    r = subprocess.run([sys.executable, DOCKET, "--version"], capture_output=True, text=True)
    assert r.stdout.strip() == f"docket {release}", r.stdout

    # Windows has no shebang, so the printed command must name the interpreter.
    assert docket_cli.run_prefix("posix", "/usr/bin/python3", DOCKET) == DOCKET
    assert docket_cli.run_prefix("nt", "C:\\Python\\python.exe", "C:\\docket\\bin\\docket") == (
        '"C:\\Python\\python.exe" "C:\\docket\\bin\\docket"'
    )

    # graph
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / ".git").mkdir()
        run(d, "init")

        run(d, "add", "Root", "--answer", "a")                                    # d1
        run(d, "add", "Ruled out", "--state", "ruled-out", "--answer", "b")        # d2
        run(d, "add", "Conjunctive child", "--answer", "c", "--because", "d1,d2")  # d3, extra support d2
        run(d, "add", "Retire the ruled-out one", "--answer", "d", "--supersedes", "d2")  # d4

        for style in ("forest", "rail", "compact"):
            r = run(d, "graph", "--style", style)
            assert r.returncode == 0, r.stderr
            for eid, question in (("d1", "Root"), ("d3", "Conjunctive child"), ("d4", "Retire")):
                assert eid in r.stdout and question[:4] in r.stdout, (style, r.stdout)

        # graph includes a retired entry; list still hides it.
        r = run(d, "graph")
        assert "Ruled out" in r.stdout, "graph must show retired entries"
        assert "retired by d4" in r.stdout
        r = run(d, "list")
        assert "Ruled out" not in r.stdout, "list must still hide retired entries"

        # d3 has two supports (d1 primary, d2 extra) and appears exactly once.
        r = run(d, "graph")
        assert r.stdout.count("d3 ") == 1 or r.stdout.count("d3   ") == 1, r.stdout
        assert "also <- d2" in r.stdout

        # --state and --find filter the graph like they filter list.
        r = run(d, "graph", "--state", "settled")
        assert "Ruled out" not in r.stdout
        assert "Root" in r.stdout
        r = run(d, "graph", "--find", "conjunctive")
        assert "Conjunctive child" in r.stdout
        assert "Retire the ruled-out one" not in r.stdout

        # A synthetic entry with two alternative sets prints the d1,d2 | d5
        # formula line, exercising the OR path the real ledger never takes.
        ledger = d / ".docket" / "ledger.jsonl"
        alt = json.dumps({
            "id": "d5", "ts": "2020-01-01T00:00:00+00:00", "state": "settled",
            "question": "Alt supports", "answer": "e", "because": [["d1", "d2"], ["d4"]],
            "cost_if_wrong": "", "session": "", "author": "x", "branch": "",
        })
        with ledger.open("a") as f:
            f.write(alt + "\n")
        r = run(d, "graph")
        assert r.returncode == 0, r.stderr
        assert "d1,d2 | d4" in r.stdout

        # A node glyph marks a node's own row. The rail drew it again on every
        # wrapped continuation row, which claimed one entry was several.
        r = run(d, "graph", "--style", "rail")
        for line in r.stdout.splitlines():
            if any(g in line for g in ("●", "○", "*", "o")):
                assert re.search(r"\bd\d+\s", line), f"glyph on a continuation row: {line!r}"

        # Several lanes waiting on one id must visibly merge back into it.
        # Without the join row the lanes vanished and the picture claimed those
        # dependents led nowhere.
        for n in range(6):
            run(d, "add", f"Fan child {n}", "--answer", "f", "--because", "d1")
        r = run(d, "graph", "--style", "rail")
        assert any(g in r.stdout for g in ("╯", "'")), r.stdout
        assert any(g in r.stdout for g in ("┴", "+")), r.stdout

        # context is untouched by any of this.
        r = run(d, "context")
        assert r.stdout.startswith("# docket:")
        assert not r.stdout.lstrip().startswith("{")

    # d22's fan: one root with 8 direct children peaks the rail at 9 columns.
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / ".git").mkdir()
        run(d, "init")
        run(d, "add", "Root", "--answer", "a")
        for _ in range(8):
            run(d, "add", "Child", "--answer", "a", "--because", "d1")

        entries = docket_cli.read(d / ".docket" / "ledger.jsonl")
        retired = docket_cli.retired_by(entries)
        nodes = {e["id"]: docket_cli._node_info(e, retired) for e in entries}
        desc = sorted(entries, key=lambda e: docket_cli._id_num(e["id"]), reverse=True)
        rows = []
        columns = []
        for e in desc:
            eid = e["id"]
            c = docket_cli._find_or_alloc(columns, eid)
            for i in range(len(columns)):
                if i != c and columns[i] == eid:
                    columns[i] = None
            rows.append(len(columns))
            supports = nodes[eid]["supports"]
            if not supports:
                columns[c] = None
            else:
                columns[c] = supports[0]
                for extra in supports[1:]:
                    docket_cli._find_or_alloc(columns, extra)
        # 8 children each open their own column before the root collapses
        # them all back into one; nothing else is running concurrently in
        # this synthetic ledger to add a 9th, unlike the real one.
        assert max(rows) == 8, rows

    # Glyph fallback degrades on an encoding that cannot carry the box-drawing set.
    class _FakeStdout:
        encoding = "ascii"
    real_stdout = docket_cli.sys.stdout
    docket_cli.sys.stdout = _FakeStdout()
    try:
        assert docket_cli._use_glyphs() is False
    finally:
        docket_cli.sys.stdout = real_stdout

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
