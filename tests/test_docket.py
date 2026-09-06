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
        assert entry["because"] == ["d1"]

        # A subdirectory shares the project's ledger.
        sub = d / "src" / "deep"
        sub.mkdir(parents=True)
        r = run(sub, "list")
        assert "Which database?" in r.stdout, "ledger lookup must walk up"

        # A malformed line is skipped, and the rest still parse.
        ledger = d / ".docket" / "ledger.jsonl"
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

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
