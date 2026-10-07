import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from docket import ledger

DOCKET = str(Path(__file__).resolve().parent.parent / "bin" / "docket")


def record(kind, ident, **kwargs):
    if kind == "decision":
        kwargs.setdefault("choice", "yes")
    return ledger.make_record(kind, f"{kind} {ident}", author="t", record_id=ident, **kwargs)


def check(records):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".git").mkdir()
        path = root / ".docket" / "ledger.jsonl"
        path.parent.mkdir()
        path.write_text("".join(json.dumps(r) + "\n" for r in records))
        env = dict(os.environ, DOCKET_HOME=str(root / "global"), DOCKET_NO_UPDATE_CHECK="1")
        return subprocess.run(
            [sys.executable, DOCKET, "check"], cwd=root, env=env, capture_output=True, text=True
        )


class CheckOrderTests(unittest.TestCase):
    def test_a_kind_may_restart_its_numbering_below_another_kinds_maximum(self):
        result = check([record("claim", "c5"), record("decision", "d1"), record("question", "q2")])
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("3 records", result.stdout)

    def test_a_number_that_does_not_increase_within_its_kind_is_a_fault(self):
        result = check([record("claim", "c5"), record("decision", "d9"), record("claim", "c3")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("line 3: id c3 does not increase past c5", result.stdout)

    def test_a_duplicate_id_is_still_reported(self):
        result = check([record("claim", "c1"), record("claim", "c1")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate id c1, first seen on line 1", result.stdout)

    def test_an_old_ledger_prints_the_migrate_instruction_once(self):
        old = [dict(record("claim", f"c{n}"), schema=2) for n in (1, 2, 3)]
        result = check(old)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count("docket migrate"), 1, result.stdout)
        self.assertIn("schema 2", result.stdout)
        self.assertNotIn("docket rebase", result.stdout)


if __name__ == "__main__":
    unittest.main()
