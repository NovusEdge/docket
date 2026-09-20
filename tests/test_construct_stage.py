"""Staging: the proposal file, resumption across runs, and review order."""

import tempfile
import unittest
from pathlib import Path

from docket.construct import schema, stage


def prop(
    path="a.md",
    anchor="Decision: one",
    kind="decision",
    choice="yes",
    scope=None,
    confidence="low",
    text="Decision made.",
):
    return schema.proposal(
        kind=kind,
        text=text,
        choice=choice,
        anchor=anchor,
        scope=scope or [],
        confidence=confidence,
        source={"path": path, "date": "2026-06-18"},
    )


class RoundTripTests(unittest.TestCase):
    def test_writes_and_reads_back_the_same_proposals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposed.jsonl"
            items = [prop(anchor="Decision: one"), prop(anchor="Decision: two")]
            stage.write(path, items)
            self.assertEqual(stage.read(path), items)

    def test_reading_a_missing_file_gives_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(stage.read(Path(tmp) / "absent.jsonl"), [])

    def test_a_unicode_anchor_survives_the_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposed.jsonl"
            item = prop(anchor="Décision : café — naïve")
            stage.write(path, [item])
            self.assertEqual(stage.read(path)[0]["anchor"], "Décision : café — naïve")


class MergeTests(unittest.TestCase):
    def test_a_rerun_keeps_an_accepted_record_accepted(self):
        old = prop()
        old["state"] = "accepted"
        fresh = prop()
        fresh["text"] = "The model worded it differently this run"
        merged = stage.merge([old], [fresh])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["state"], "accepted")

    def test_a_rerun_keeps_a_rejected_record_rejected(self):
        old = prop()
        old["state"] = "rejected"
        merged = stage.merge([old], [prop()])
        self.assertEqual(merged[0]["state"], "rejected")

    def test_a_rerun_takes_the_fresh_wording_for_a_still_staged_record(self):
        old = prop()
        fresh = prop()
        fresh["text"] = "Reworded"
        merged = stage.merge([old], [fresh])
        self.assertEqual(merged[0]["text"], "Reworded")

    def test_an_edited_source_line_stages_the_record_again(self):
        # The anchor is the key. Editing the source text the record was
        # accepted against must put it back in front of a human.
        old = prop(anchor="Decision: one")
        old["state"] = "accepted"
        merged = stage.merge([old], [prop(anchor="Decision: one, revised")])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["state"], "staged")

    def test_a_record_no_longer_extracted_is_dropped(self):
        old = prop(anchor="Decision: gone")
        merged = stage.merge([old], [prop(anchor="Decision: here")])
        self.assertEqual([m["anchor"] for m in merged], ["Decision: here"])

    def test_merging_into_an_empty_stage_stages_everything(self):
        merged = stage.merge([], [prop(), prop(anchor="Decision: two")])
        self.assertEqual([m["state"] for m in merged], ["staged", "staged"])


class ResolutionTests(unittest.TestCase):
    def test_a_scope_matching_a_live_file_resolves(self):
        self.assertTrue(
            stage.resolves(prop(scope=["docket/context.py"]), {"docket/context.py", "README.md"})
        )

    def test_a_glob_resolves_against_a_live_file(self):
        self.assertTrue(stage.resolves(prop(scope=["docket/**"]), {"docket/context.py"}))

    def test_a_scope_matching_nothing_does_not_resolve(self):
        self.assertFalse(stage.resolves(prop(scope=["db/labels_v2.py"]), {"docket/context.py"}))

    def test_a_record_with_no_scope_does_not_resolve(self):
        # 29 of the spike's 61 records carried no scope at all. Absence is not
        # evidence the record is live.
        self.assertFalse(stage.resolves(prop(scope=[]), {"docket/context.py"}))

    def test_one_resolving_entry_is_enough(self):
        self.assertTrue(
            stage.resolves(prop(scope=["gone.py", "docket/context.py"]), {"docket/context.py"})
        )


class ReviewOrderTests(unittest.TestCase):
    def test_groups_by_source_document(self):
        items = [
            prop(path="b.md", anchor="one"),
            prop(path="a.md", anchor="two"),
            prop(path="b.md", anchor="three"),
        ]
        groups = stage.review_groups(items, live={"x"})
        self.assertEqual([name for name, _ in groups], ["a.md", "b.md"])
        self.assertEqual(len(dict(groups)["b.md"]), 2)

    def test_sorts_high_confidence_first_inside_a_group(self):
        items = [
            prop(anchor="low one", confidence="low"),
            prop(anchor="high one", confidence="high"),
            prop(anchor="medium one", confidence="medium"),
        ]
        groups = stage.review_groups(items, live={"x"})
        self.assertEqual(
            [p["anchor"] for p in dict(groups)["a.md"]], ["high one", "medium one", "low one"]
        )

    def test_sinks_a_record_whose_scope_resolves_to_nothing(self):
        live = {"docket/context.py"}
        items = [
            prop(anchor="stale", confidence="high", scope=["gone.py"]),
            prop(anchor="live", confidence="low", scope=["docket/context.py"]),
        ]
        groups = stage.review_groups(items, live=live)
        self.assertEqual([p["anchor"] for p in dict(groups)["a.md"]], ["live", "stale"])

    def test_an_accepted_record_is_not_offered_for_review(self):
        accepted = prop(anchor="done")
        accepted["state"] = "accepted"
        groups = stage.review_groups([accepted, prop(anchor="todo")], live={"x"})
        self.assertEqual([p["anchor"] for p in dict(groups)["a.md"]], ["todo"])


class ResolutionRateTests(unittest.TestCase):
    def test_reports_the_share_of_scoped_records_that_resolve(self):
        live = {"docket/context.py"}
        items = [
            prop(anchor="a", scope=["docket/context.py"]),
            prop(anchor="b", scope=["gone.py"]),
            prop(anchor="c", scope=[]),
        ]
        # Two carry a scope; one of them resolves.
        self.assertEqual(stage.resolution_rate(items, live), (1, 2))

    def test_a_set_with_no_scoped_records_reports_zero_of_zero(self):
        self.assertEqual(stage.resolution_rate([prop(scope=[])], {"x"}), (0, 0))


if __name__ == "__main__":
    unittest.main()
