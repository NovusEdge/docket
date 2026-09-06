"""Run with: python3 tests/test_docket.py"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DOCKET = str(Path(__file__).resolve().parent.parent / "bin" / "docket")


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

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
