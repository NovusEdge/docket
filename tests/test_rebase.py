import json
import tempfile
import unittest
from pathlib import Path

from docket.ledger import make_record, read
from docket.rebase import RebaseError, common_prefix, renumber


def claim(ident, text, **kwargs):
    return make_record("claim", text, state="accepted", author="t", record_id=ident, **kwargs)


def decision(ident, text, **kwargs):
    return make_record("decision", text, choice="yes", author="t", record_id=ident, **kwargs)


class RebaseTests(unittest.TestCase):
    def test_common_prefix_counts_identical_leading_records(self):
        base = [claim("c1", "Shared"), claim("c2", "Also shared")]
        mine = base + [claim("c3", "Mine")]
        theirs = base + [claim("c3", "Theirs")]
        self.assertEqual(common_prefix(mine, theirs), 2)

    def test_renumber_continues_the_sequence_and_rewrites_inner_references(self):
        base = [claim("c1", "Shared premise")]
        mine = base + [claim("c2", "Mine")]
        theirs = base + [
            claim("c2", "Their premise"),
            decision("d3", "Their decision", supports=[["c2"], ["c1"]], depends_on=["c2"]),
        ]
        tail, mapping = renumber(mine, theirs)
        self.assertEqual(mapping, {"c2": "c3", "d3": "d4"})
        self.assertEqual([row["id"] for row in tail], ["c3", "d4"])
        # The inner reference follows the rename; the prefix reference does not.
        self.assertEqual(tail[1]["supports"], [["c3"], ["c1"]])
        self.assertEqual(tail[1]["depends_on"], ["c3"])

    def test_renumbered_tail_appends_to_a_valid_ledger(self):
        base = [claim("c1", "Shared premise")]
        mine = base + [claim("c2", "Mine")]
        theirs = base + [decision("d2", "Theirs", depends_on=["c1"])]
        tail, _ = renumber(mine, theirs)
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "ledger.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in mine + tail) + "\n")
            self.assertEqual(len(read(path)), 3)

    def test_a_second_supersession_of_one_record_is_refused(self):
        base = [claim("c1", "Shared premise")]
        mine = base + [claim("c2", "Mine", supersedes=["c1"])]
        theirs = base + [claim("c2", "Theirs", supersedes=["c1"])]
        with self.assertRaises(RebaseError) as caught:
            renumber(mine, theirs)
        self.assertIn("c1", str(caught.exception))

    def test_a_migrated_record_keeps_its_relation_map_consistent(self):
        base = [claim("c1", "Shared premise")]
        theirs = base + [
            claim("c2", "Their premise"),
            decision("d3", "Their decision", depends_on=["c2"]),
        ]
        # Every record in a migrated ledger carries this block, and validation
        # requires mapped_* to equal the record's relations.
        theirs[2]["legacy"] = {
            "raw": {"because": ["c2"]},
            "relation_map": {
                "source_because": ["c2"],
                "mapped_depends_on": ["c2"],
                "overrides": [],
            },
        }
        mine = base + [claim("c2", "Mine")]
        tail, _ = renumber(mine, theirs)
        self.assertEqual(tail[1]["depends_on"], ["c3"])
        self.assertEqual(tail[1]["legacy"]["relation_map"]["mapped_depends_on"], ["c3"])
        # The pre-migration record is history and does not move.
        self.assertEqual(tail[1]["legacy"]["relation_map"]["source_because"], ["c2"])

    def test_identical_histories_produce_an_empty_tail(self):
        base = [claim("c1", "Shared premise")]
        tail, mapping = renumber(base, base)
        self.assertEqual(tail, [])
        self.assertEqual(mapping, {})

    def test_an_incoming_correction_follows_its_renumbered_record(self):
        from docket import corrections

        shared = make_record("claim", "Shared.", author="t", record_id="c1")
        mine = [shared, make_record("claim", "Mine.", author="t", record_id="c2")]
        theirs_record = make_record("claim", "Theirs.", author="t", record_id="c2")
        fix = corrections.make("c2", {"scope": ["a.py"]}, author="t")
        fix["id"] = "c2.1"
        tail, mapping = renumber(mine, [shared, theirs_record, fix])
        self.assertEqual(mapping, {"c2": "c3", "c2.1": "c3.1"})
        self.assertEqual(tail[1]["corrects"], "c3")

    def test_both_branches_corrected_one_record(self):
        from docket import corrections

        shared = make_record("claim", "Shared.", author="t", record_id="c1")
        mine_fix = corrections.make("c1", {"scope": ["a.py"]}, author="t")
        mine_fix["id"] = "c1.1"
        their_fix = corrections.make("c1", {"scope": ["b.py"]}, author="t")
        their_fix["id"] = "c1.1"
        their_second = corrections.make("c1", {"revisit": "Later."}, author="t")
        their_second["id"] = "c1.2"
        tail, mapping = renumber([shared, mine_fix], [shared, their_fix, their_second])
        self.assertEqual(mapping, {"c1.1": "c1.2", "c1.2": "c1.3"})
        self.assertEqual([item["corrects"] for item in tail], ["c1", "c1"])


if __name__ == "__main__":
    unittest.main()
