"""Run with: python3 tests/test_docket.py"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DOCKET = str(Path(__file__).resolve().parent.parent / "bin" / "docket")


def run(cwd, *args):
    return subprocess.run(
        [sys.executable, DOCKET, *args], cwd=cwd, capture_output=True, text=True
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        r = run(d, "context")
        assert r.returncode == 0, r.stderr
        assert r.stdout == "", f"empty project must cost no context, got {r.stdout!r}"

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

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
