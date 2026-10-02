import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.ledger as ledger
from docket import support

LEDGER = Path(__file__).parent.parent / ".docket" / "ledger.jsonl"


class RepositoryLedgerTests(unittest.TestCase):
    @unittest.skipUnless(LEDGER.exists(), "no project ledger in this checkout")
    def test_no_current_record_loses_its_grounds(self):
        # This ledger records no rejection, revocation or reversal, so nothing
        # is lost to one; cycles built by forward resolution are flagged, not lost.
        projected = ledger.project(ledger.read(LEDGER), validated=True)
        lost = {e["id"]: e["lost_grounds"] for e in projected if support.surfaced(e, "unsupported")}
        self.assertEqual(lost, {})


if __name__ == "__main__":
    unittest.main()
