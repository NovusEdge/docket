import json
import tempfile
import unittest
from pathlib import Path

from docket.ledger import make_record, read
from docket.rebase import RebaseError, common_prefix, merge, renumber


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

    def test_a_tail_already_absorbed_is_not_appended_again(self):
        # main renumbered the branch's c2 to c3; merging the branch again must
        # recognise c3 as the same recording.
        shared = [claim("c1", "Shared premise")]
        branch = shared + [claim("c2", "Branch claim", supports=[["c1"]])]
        main = shared + [claim("c2", "Main claim")]
        tail, mapping = renumber(main, branch)
        merged_main = main + tail
        self.assertEqual(mapping, {"c2": "c3"})
        again, mapping = renumber(merged_main, branch)
        self.assertEqual((again, mapping), ([], {}))

    def test_merging_back_the_other_way_appends_only_the_missing_record(self):
        shared = [claim("c1", "Shared premise")]
        branch = shared + [claim("c2", "Branch claim")]
        main = shared + [claim("c2", "Main claim")]
        merged_main = main + renumber(main, branch)[0]
        tail, mapping = renumber(branch, merged_main)
        self.assertEqual([r["text"] for r in tail], ["Main claim"])
        self.assertEqual(mapping, {"c2": "c3"})

    def test_a_record_matched_under_a_new_id_carries_that_id_into_later_references(self):
        shared = [claim("c1", "Shared premise")]
        branch = shared + [claim("c2", "Branch claim")]
        main = shared + [claim("c2", "Main claim")]
        merged_main = main + renumber(main, branch)[0]
        branch_later = branch + [decision("d3", "Uses it", supports=[["c2"]])]
        tail, mapping = renumber(merged_main, branch_later)
        self.assertEqual(mapping, {"d3": "d4"})
        self.assertEqual(tail[0]["supports"], [["c3"]])

    def test_two_identical_looking_reviews_of_different_records_stay_distinct(self):
        from docket import reviews

        shared = [claim("c1", "One"), claim("c2", "Two")]
        first = reviews.make("c1", author="t", ts="2026-10-03T00:00:00+00:00")
        first["id"] = "c1.r1"
        second = reviews.make("c2", author="t", ts="2026-10-03T00:00:00+00:00")
        second["id"] = "c2.r1"
        mine = shared + [first]
        theirs = shared + [second]
        tail, mapping = renumber(mine, theirs)
        self.assertEqual(mapping, {"c2.r1": "c2.r1"})
        self.assertEqual(tail[0]["reviews"], "c2")

    def test_one_ours_record_absorbs_only_one_identical_theirs_record(self):
        shared = [claim("c1", "Shared")]
        mine = shared + [claim("c2", "Other"), claim("c3", "Same")]
        theirs = shared + [claim("c2", "Same"), claim("c3", "Same")]
        # make_record stamps ts per call, so pin it to make the copies equal.
        for row in mine[1:] + theirs[1:]:
            row["ts"] = "2026-10-03T00:00:00+00:00"
        tail, mapping = renumber(mine, theirs)
        # Their c2 consumes our c3; their c3 has nothing left to match.
        self.assertEqual(mapping, {"c3": "c4"})
        self.assertEqual(len(tail), 1)

    def test_a_record_only_in_base_is_not_brought_back(self):
        # Cherry-pick: THEIRS is the picked commit's whole ledger, BASE is its
        # parent's. Only the picked commit's own record is new.
        shared = [claim("c1", "Shared")]
        earlier = claim("c2", "Earlier branch claim")
        picked = claim("c3", "Picked claim")
        main = shared + [claim("c2", "Main claim")]
        tail, mapping = merge(shared + [earlier], main, shared + [earlier, picked])
        self.assertEqual([r["text"] for r in tail], ["Picked claim"])
        self.assertEqual(mapping, {"c3": "c3"})

    def test_citing_a_record_only_in_base_is_refused(self):
        shared = [claim("c1", "Shared")]
        earlier = claim("c2", "Earlier branch claim")
        picked = decision("d3", "Picked decision", supports=[["c2"]])
        main = shared + [claim("c2", "Main claim")]
        with self.assertRaises(RebaseError) as caught:
            merge(shared + [earlier], main, shared + [earlier, picked])
        self.assertIn("c2", str(caught.exception))

    def test_a_matched_supersession_is_not_refused(self):
        # Our side already absorbed their replacement as c3, so c1 is retired
        # on our side by the very record that arrives again.
        shared = [claim("c1", "Shared premise")]
        replacement = claim("c2", "Replacement", supersedes=["c1"])
        absorbed = dict(replacement, id="c3")
        mine = shared + [claim("c2", "Ours"), absorbed]
        tail, mapping = renumber(mine, shared + [replacement])
        self.assertEqual((tail, mapping), ([], {}))


if __name__ == "__main__":
    unittest.main()
