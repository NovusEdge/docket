import copy
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from docket import corrections, migrate, reviews
from docket.cli import main
from docket.ledger import make_record, read
from docket.rebase import (
    PROSE_FIELDS,
    ProseChange,
    RebaseError,
    _key,
    common_prefix,
    merge,
    renumber,
    renumber_per_kind,
    rewrite_prose,
)


def claim(ident, text, **kwargs):
    return make_record("claim", text, state="accepted", author="t", record_id=ident, **kwargs)


def decision(ident, text, **kwargs):
    kwargs.setdefault("choice", "yes")
    return make_record("decision", text, author="t", record_id=ident, **kwargs)


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
        self.assertEqual(mapping, {"c2": "c3", "d3": "d1"})
        self.assertEqual([row["id"] for row in tail], ["c3", "d1"])
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
        self.assertEqual(mapping, {"d3": "d1"})
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


PINNED = "2026-10-03T00:00:00+00:00"


def question(ident, text, **kwargs):
    return make_record("question", text, author="t", record_id=ident, **kwargs)


def mixed_ledger():
    """Schema-2 ids from one global counter, one line of every kind, ts pinned."""

    rows = [
        claim("c1", "Base premise"),
        decision("d2", "Use the log", supports=[["c1"]]),
        claim("c3", "Log holds d2 and c1"),
        question("q4", "Where does it live"),
        decision(
            "d5",
            "Move it",
            supports=[["c3", "c1"], ["d2"]],
            depends_on=["d2"],
            answers=["q4"],
            supersedes=["d2"],
        ),
        claim("c6", "Later premise"),
    ]
    fix = corrections.make("c3", {"text": "Log holds d5."}, reason="d5 changed", author="t")
    fix["id"] = "c3.1"
    rows.append(fix)
    review = reviews.make("d5", note="Rechecked d5 against c3", author="t")
    review["id"] = "d5.r1"
    review["grounds"] = {"c3": "c3", "d2": "d5"}
    rows.append(review)
    for row in rows:
        row["ts"] = PINNED
    return rows


class RewriteProseTests(unittest.TestCase):
    def test_one_lookup_per_token_so_shifted_ids_do_not_chain(self):
        mapping = {"c3": "c2", "c2": "c1"}
        self.assertEqual(
            rewrite_prose("c3 then c2, not c3 again", mapping), "c2 then c1, not c2 again"
        )

    def test_a_token_naming_no_mapped_id_is_left_alone(self):
        mapping = {"c2": "c1"}
        self.assertEqual(
            rewrite_prose("c99, q7, c2 and abc2 and c02", mapping), "c99, q7, c1 and abc2 and c02"
        )

    def test_lists_are_rewritten_element_wise_and_other_values_pass_through(self):
        mapping = {"d3": "d1"}
        self.assertEqual(rewrite_prose(["keep d3", "drop it"], mapping), ["keep d1", "drop it"])
        self.assertEqual(rewrite_prose(["d3", 7, None], mapping), ["d1", 7, None])
        self.assertEqual(rewrite_prose(5, mapping), 5)
        self.assertIsNone(rewrite_prose(None, mapping))

    def test_via_resolves_a_token_before_the_mapping_does(self):
        # A schema-1 id in a legacy line's prose names the record whose
        # legacy.source_id it is, not the schema-2 record that shares its number.
        mapping = {"c4": "c2", "d4": "d1"}
        via = {"d4": "c4"}
        self.assertEqual(rewrite_prose("was d4, near c4", mapping, via), "was c2, near c2")
        self.assertEqual(rewrite_prose("was d4, near c4", mapping), "was d1, near c2")

    def test_prose_fields_are_the_six_wording_keys(self):
        self.assertEqual(
            PROSE_FIELDS,
            ("text", "choice", "alternatives", "rationale", "cost_if_wrong", "revisit"),
        )


class RenumberPerKindTests(unittest.TestCase):
    def test_each_kind_counts_from_one_in_file_order(self):
        rows = mixed_ledger()
        untouched = copy.deepcopy(rows)
        out, mapping, _ = renumber_per_kind(rows)
        self.assertEqual(rows, untouched)
        self.assertEqual(
            [row["id"] for row in out],
            ["c1", "d1", "c2", "q1", "d2", "c3", "c2.1", "d2.r1"],
        )
        self.assertEqual(
            mapping,
            {"c1": "c1", "d2": "d1", "c3": "c2", "q4": "q1", "d5": "d2", "c6": "c3"},
        )

    def test_corrections_and_reviews_keep_their_suffix_and_follow_their_target(self):
        out, _, _ = renumber_per_kind(mixed_ledger())
        fix, review = out[6], out[7]
        self.assertEqual((fix["id"], fix["corrects"]), ("c2.1", "c2"))
        self.assertEqual((review["id"], review["reviews"]), ("d2.r1", "d2"))
        self.assertEqual(review["grounds"], {"c2": "c2", "d1": "d2"})

    def test_relations_are_rewritten(self):
        out, _, _ = renumber_per_kind(mixed_ledger())
        self.assertEqual(out[1]["supports"], [["c1"]])
        moved = out[4]
        self.assertEqual(moved["supports"], [["c2", "c1"], ["d1"]])
        self.assertEqual(moved["depends_on"], ["d1"])
        self.assertEqual(moved["answers"], ["q1"])
        self.assertEqual(moved["supersedes"], ["d1"])

    def test_prose_mentions_follow_the_mapping_without_chaining(self):
        out, _, _ = renumber_per_kind(mixed_ledger())
        self.assertEqual(out[2]["text"], "Log holds d1 and c1")
        # Old d5 is now d2, and old d2 is now d1: a chained rewrite would say d1.
        self.assertEqual(out[6]["fields"]["text"], "Log holds d2.")
        self.assertEqual(out[6]["reason"], "d2 changed")
        self.assertEqual(out[7]["note"], "Rechecked d2 against c2")

    def test_every_prose_field_is_rewritten_and_an_unmapped_token_stays(self):
        rows = [
            decision("d1", "Base"),
            claim("c2", "Premise"),
            decision(
                "d3",
                "Rests on c2 and d1",
                choice="Use c2, not c99",
                alternatives=["keep d1", "drop c2"],
                rationale="Because c2.",
                cost_if_wrong="Redo d1 and c2.",
                revisit="When c2 changes.",
            ),
        ]
        fix = corrections.make(
            "d3",
            {
                "text": "Now rests on c2.",
                "alternatives": ["keep d1", "drop c2"],
                "rationale": "c2 again.",
                "scope": ["c2"],
            },
            author="t",
        )
        fix["id"] = "d3.1"
        out, _, _ = renumber_per_kind(rows + [fix])
        row = out[2]
        self.assertEqual(row["id"], "d2")
        self.assertEqual(row["text"], "Rests on c1 and d1")
        self.assertEqual(row["choice"], "Use c1, not c99")
        self.assertEqual(row["alternatives"], ["keep d1", "drop c1"])
        self.assertEqual(row["rationale"], "Because c1.")
        self.assertEqual(row["cost_if_wrong"], "Redo d1 and c1.")
        self.assertEqual(row["revisit"], "When c1 changes.")
        fields = out[3]["fields"]
        self.assertEqual(fields["text"], "Now rests on c1.")
        self.assertEqual(fields["alternatives"], ["keep d1", "drop c1"])
        self.assertEqual(fields["rationale"], "c1 again.")
        self.assertEqual(fields["scope"], ["c2"])

    def test_a_line_that_mentions_its_own_id_gets_the_new_one(self):
        out, _, _ = renumber_per_kind([decision("d1", "Base"), claim("c2", "Calls itself c2")])
        self.assertEqual(out[1]["text"], "Calls itself c1")

    def test_legacy_scope_evidence_and_schema_are_not_touched(self):
        rows = [decision("d1", "Base"), claim("c2", "Premise", scope=["c2"])]
        rows[1]["legacy"] = {"mapped_supports": ["c2", "d1"]}
        rows[1]["evidence"] = [{"kind": "note", "ref": "see c2"}]
        out, _, _ = renumber_per_kind(rows)
        row = out[1]
        self.assertEqual(row["id"], "c1")
        self.assertEqual(row["scope"], ["c2"])
        self.assertEqual(row["legacy"], {"mapped_supports": ["c2", "d1"]})
        self.assertEqual(row["evidence"], [{"kind": "note", "ref": "see c2"}])
        self.assertEqual(row["schema"], rows[1]["schema"])

    def test_a_legacy_line_resolves_prose_through_its_source_id_first(self):
        # Schema-1 c4 became schema-2 d4; its prose still says "c4" for itself.
        # Without source_id, "c4" would map to the schema-2 claim c4.
        first = claim("c1", "Root")
        second = claim("c2", "Other")
        third = decision("d3", "Legacy decision")
        third["legacy"] = {"source_id": "c3"}
        fourth = claim("c4", "A claim")
        fourth["text"] = "Not the legacy c3, only c4"
        fourth["legacy"] = {"source_id": "d4"}
        fifth = decision("d5", "Mentions c3 as written")
        out, _, _ = renumber_per_kind([first, second, third, fourth, fifth])
        # c3 in c4's prose is the legacy source of d3 -> d1; c4 is the schema-2 claim -> c3.
        self.assertEqual(out[3]["text"], "Not the legacy d1, only c3")
        # A line without legacy resolves through the mapping alone, and c3 is unmapped.
        self.assertEqual(out[4]["text"], "Mentions c3 as written")

    def test_migrated_from_is_set_on_claims_decisions_and_questions_only(self):
        rows = mixed_ledger()
        out, _, _ = renumber_per_kind(rows)
        for old, new in zip(rows, out):
            if old["kind"] in ("claim", "decision", "question"):
                self.assertEqual(new["migrated_from"], old["id"])
            else:
                self.assertNotIn("migrated_from", new)

    def test_renumbering_a_prefix_equals_the_prefix_of_renumbering_the_whole(self):
        rows = mixed_ledger()
        whole = renumber_per_kind(rows)[0]
        for k in range(len(rows) + 1):
            with self.subTest(k=k):
                self.assertEqual(renumber_per_kind(rows[:k])[0], whole[:k])

    def test_a_duplicate_old_id_is_refused(self):
        with self.assertRaises(RebaseError) as caught:
            renumber_per_kind([claim("c1", "One"), claim("c1", "Two")])
        self.assertIn("c1", str(caught.exception))

    def test_a_citation_of_an_id_not_yet_defined_is_refused(self):
        for rows in (
            [decision("d1", "Early", depends_on=["c2"]), claim("c2", "Late")],
            [claim("c1", "Only"), decision("d2", "Cites", supports=[["c9"]])],
        ):
            with self.subTest(rows=[r["id"] for r in rows]):
                with self.assertRaises(RebaseError):
                    renumber_per_kind(rows)

    def test_a_correction_or_review_of_a_missing_target_is_refused(self):
        fix = corrections.make("c9", {"text": "x"}, author="t")
        fix["id"] = "c9.1"
        with self.assertRaises(RebaseError):
            renumber_per_kind([claim("c1", "Only"), fix])
        review = reviews.make("c9", author="t")
        review["id"] = "c9.r1"
        review["grounds"] = {"c1": "c1"}
        with self.assertRaises(RebaseError):
            renumber_per_kind([claim("c1", "Only"), review])


def raw(kind, ident, text, **extra):
    return {"schema": 2, "kind": kind, "id": ident, "text": text, **extra}


class RenumberGoldenTests(unittest.TestCase):
    """Pins renumber_per_kind byte for byte.

    Two branches migrated by docket versions whose rules differ share no
    prefix, so changing this output is a format change that needs a new schema.
    """

    OLD = [
        raw("claim", "c1", "Root premise"),
        raw("decision", "d2", "Adopt the log", supports=[["c1"]]),
        raw("claim", "c3", "Was d3; see c1 and d2", legacy={"source_id": "d3"}),
        raw("question", "q4", "Which of c1 or d2"),
        raw(
            "decision",
            "d5",
            "Settles q4",
            alternatives=["keep d2", "drop c3"],
            rationale="Unlike c9",
            depends_on=["d2"],
            answers=["q4"],
        ),
        {
            "schema": 2,
            "kind": "correction",
            "id": "d5.1",
            "corrects": "d5",
            "fields": {"text": "Settles q4 for d2", "scope": ["c3"]},
            "reason": "see c3",
        },
        {
            "schema": 2,
            "kind": "review",
            "id": "d5.r1",
            "reviews": "d5",
            "grounds": {"c3": "c3"},
            "note": "ok per q4",
        },
    ]

    NEW = [
        raw("claim", "c1", "Root premise", migrated_from="c1"),
        raw("decision", "d1", "Adopt the log", supports=[["c1"]], migrated_from="d2"),
        raw(
            "claim",
            "c2",
            "Was c2; see c1 and d1",
            legacy={"source_id": "d3"},
            migrated_from="c3",
        ),
        raw("question", "q1", "Which of c1 or d1", migrated_from="q4"),
        raw(
            "decision",
            "d2",
            "Settles q1",
            alternatives=["keep d1", "drop c2"],
            rationale="Unlike c9",
            depends_on=["d1"],
            answers=["q1"],
            migrated_from="d5",
        ),
        {
            "schema": 2,
            "kind": "correction",
            "id": "d2.1",
            "corrects": "d2",
            "fields": {"text": "Settles q1 for d1", "scope": ["c3"]},
            "reason": "see c2",
        },
        {
            "schema": 2,
            "kind": "review",
            "id": "d2.r1",
            "reviews": "d2",
            "grounds": {"c2": "c2"},
            "note": "ok per q1",
        },
    ]

    def test_output_mapping_and_report_are_fixed(self):
        out, mapping, changes = renumber_per_kind(copy.deepcopy(self.OLD))
        self.assertEqual(out, self.NEW)
        self.assertEqual(mapping, {"c1": "c1", "d2": "d1", "c3": "c2", "q4": "q1", "d5": "d2"})
        self.assertEqual(
            changes,
            [
                ProseChange("c3", "text", "Was d3; see c1 and d2", "Was c2; see c1 and d1"),
                ProseChange("q4", "text", "Which of c1 or d2", "Which of c1 or d1"),
                ProseChange("d5", "text", "Settles q4", "Settles q1"),
                ProseChange("d5", "alternatives", "keep d2", "keep d1"),
                ProseChange("d5", "alternatives", "drop c3", "drop c2"),
                ProseChange("d5", "rationale", "c9", None),
                ProseChange("d5.1", "text", "Settles q4 for d2", "Settles q1 for d1"),
                ProseChange("d5.1", "reason", "see c3", "see c2"),
                ProseChange("d5.r1", "note", "ok per q4", "ok per q1"),
            ],
        )


class MatchKeyTests(unittest.TestCase):
    def test_the_key_ignores_id_migrated_from_and_id_tokens_in_prose(self):
        left = decision("d3", "Uses c2", supports=[["c2"]], rationale="see d1")
        right = dict(left, id="d1", migrated_from="d3", text="Uses c1", rationale="see d9")
        self.assertEqual(_key(left), _key(right))

    def test_the_key_still_tells_apart_relations_and_other_wording(self):
        left = decision("d3", "Uses c2", supports=[["c2"]])
        self.assertNotEqual(_key(left), _key(dict(left, supports=[["c1"]])))
        self.assertNotEqual(_key(left), _key(dict(left, text="Uses c2 now")))

    def test_correction_fields_and_reason_and_review_note_are_masked(self):
        one = corrections.make("c1", {"text": "see c2"}, reason="d3 was wrong", ts=PINNED)
        two = corrections.make("c1", {"text": "see c7"}, reason="d9 was wrong", ts=PINNED)
        self.assertEqual(_key(one), _key(two))
        three = reviews.make("c1", note="c2 holds", ts=PINNED)
        four = reviews.make("c1", note="c8 holds", ts=PINNED)
        self.assertEqual(_key(three), _key(four))
        five = corrections.make("c1", {"text": "other"}, reason="d3 was wrong", ts=PINNED)
        self.assertNotEqual(_key(one), _key(five))


class MergeProseTests(unittest.TestCase):
    def branch_pair(self):
        shared = [claim("c1", "Shared premise")]
        branch = shared + [
            claim("c2", "Branch claim"),
            decision("d3", "Uses c2", supports=[["c2"]]),
        ]
        main = shared + [claim("c2", "Main claim")]
        for row in branch[1:] + main[1:]:
            row["ts"] = PINNED
        return shared, branch, main

    def test_a_merge_rewrites_prose_in_the_appended_tail(self):
        _, branch, main = self.branch_pair()
        tail, mapping = renumber(main, branch)
        self.assertEqual(mapping["c2"], "c3")
        self.assertEqual(tail[1]["text"], "Uses c3")
        self.assertEqual(tail[1]["supports"], [["c3"]])

    def test_a_second_merge_of_the_same_branch_appends_nothing(self):
        _, branch, main = self.branch_pair()
        merged = main + renumber(main, branch)[0]
        self.assertEqual(renumber(merged, branch), ([], {}))

    def test_each_side_migrating_after_a_pre_migration_merge_still_merges_cleanly(self):
        base = [claim("c1", "Shared")]
        main = base + [decision("d2", "Main decision", supports=[["c1"]])]
        # The branch merged main under the old code: main's d2 landed as d3.
        branch = base + [
            claim("c2", "Branch claim"),
            dict(main[1], id="d3"),
            decision("d4", "Builds on d3", depends_on=["d3"]),
        ]
        for row in main[1:] + branch[1:]:
            row["ts"] = PINNED
        base_m = renumber_per_kind(base)[0]
        main_m = renumber_per_kind(main)[0]
        branch_m = renumber_per_kind(branch)[0]
        # Same decision, migrated_from d2 on main and d3 on the branch.
        self.assertNotEqual(main_m[1]["migrated_from"], branch_m[2]["migrated_from"])
        tail, _ = merge(base_m, main_m, branch_m)
        self.assertEqual([r["text"] for r in tail], ["Branch claim", "Builds on d1"])
        self.assertEqual(tail[1]["depends_on"], ["d1"])
        self.assertEqual(merge(base_m, main_m + tail, branch_m), ([], {}))


def v2(records):
    return [dict(r, schema=2) for r in records]


def upgraded(records):
    return migrate.renumber_step(v2(records))[0]


def write_lines(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


class RebaseAcrossMigrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        subprocess.run(
            ["git", "-C", str(self.root), "init", "-b", "main"], check=True, capture_output=True
        )
        (self.root / ".docket").mkdir()
        self.ledger = self.root / ".docket" / "ledger.jsonl"
        self.other = self.root / "other.jsonl"
        cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        self.shared = [
            claim("c1", "Shared premise"),
            decision("d2", "Cache layer sits behind reads", supports=[["c1"]]),
        ]

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_two_ledgers_migrated_separately_rebase_cleanly(self):
        write_lines(self.ledger, upgraded(self.shared + [claim("c3", "Ours only")]))
        write_lines(self.other, upgraded(self.shared + [claim("c3", "Their premise")]))
        code, _, _ = self.run_cli("rebase", str(self.other))
        self.assertEqual(code, 0)
        merged = read(self.ledger)
        self.assertEqual([r["id"] for r in merged], ["c1", "d1", "c2", "c3"])
        self.assertEqual(merged[3]["text"], "Their premise")

    def test_a_schema_2_other_is_refused_and_the_ledger_left_alone(self):
        write_lines(self.ledger, upgraded(self.shared))
        write_lines(self.other, v2(self.shared + [claim("c3", "Their premise")]))
        before = self.ledger.read_bytes()
        code, _, err = self.run_cli("rebase", str(self.other))
        self.assertEqual(code, 1)
        self.assertIn("docket migrate", err)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_a_schema_2_working_ledger_is_refused_and_left_alone(self):
        write_lines(self.ledger, v2(self.shared))
        write_lines(self.other, upgraded(self.shared))
        before = self.ledger.read_bytes()
        code, _, err = self.run_cli("rebase", str(self.other))
        self.assertEqual(code, 1)
        self.assertIn("docket migrate", err)
        self.assertEqual(self.ledger.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
