"""Pass 2: the payload a linker sees, and the edges it is allowed to propose."""

import unittest

from docket.construct import link, schema


def prop(anchor, kind="decision", choice="yes", text="Question?", date="2026-06-18",
         path="a.md", rationale="because", scope=None):
    return schema.proposal(kind=kind, text=text, choice=choice, anchor=anchor,
                           rationale=rationale, scope=scope or [],
                           source={"path": path, "date": date})


class PayloadTests(unittest.TestCase):
    def test_labels_each_record_so_a_model_can_reference_it(self):
        rows = link.payload([prop("one"), prop("two")])
        self.assertEqual([r["id"] for r in rows], ["p1", "p2"])

    def test_carries_only_what_linking_needs(self):
        rows = link.payload([prop("one")])
        self.assertEqual(set(rows[0]), {"id", "kind", "text", "choice", "path", "date"})

    def test_omits_the_anchor_and_rationale_to_keep_the_call_small(self):
        # The whole point of sending proposals instead of documents: the spike's
        # 61 records are 2.8k tokens of metadata against 15k words of source.
        rows = link.payload([prop("one")])
        self.assertNotIn("anchor", rows[0])
        self.assertNotIn("rationale", rows[0])

    def test_a_label_maps_back_to_the_record_key(self):
        items = [prop("one"), prop("two")]
        labels = link.labels(items)
        self.assertEqual(labels["p2"], items[1]["key"])


class ReferenceTests(unittest.TestCase):
    def test_keeps_an_edge_between_known_records(self):
        items = [prop("one"), prop("two")]
        edges, dropped = link.validate([{"kind": "supports", "from": "p2", "to": "p1"}], items)
        self.assertEqual(len(edges), 1)
        self.assertEqual(dropped, [])

    def test_drops_an_edge_naming_a_record_that_does_not_exist(self):
        items = [prop("one")]
        edges, dropped = link.validate([{"kind": "supports", "from": "p1", "to": "p9"}], items)
        self.assertEqual(edges, [])
        self.assertIn("p9", dropped[0])

    def test_drops_an_edge_from_a_record_to_itself(self):
        items = [prop("one")]
        edges, dropped = link.validate([{"kind": "supports", "from": "p1", "to": "p1"}], items)
        self.assertEqual(edges, [])
        self.assertTrue(dropped)

    def test_drops_an_edge_of_an_unknown_kind(self):
        items = [prop("one"), prop("two")]
        edges, dropped = link.validate([{"kind": "resembles", "from": "p1", "to": "p2"}], items)
        self.assertEqual(edges, [])
        self.assertIn("resembles", dropped[0])


class SupersedesTests(unittest.TestCase):
    def test_keeps_a_later_record_superseding_an_earlier_one(self):
        items = [prop("old", date="2026-01-01"), prop("new", date="2026-06-01")]
        edges, dropped = link.validate([{"kind": "supersedes", "from": "p2", "to": "p1"}], items)
        self.assertEqual(len(edges), 1)

    def test_drops_an_earlier_record_superseding_a_later_one(self):
        items = [prop("old", date="2026-01-01"), prop("new", date="2026-06-01")]
        edges, dropped = link.validate([{"kind": "supersedes", "from": "p1", "to": "p2"}], items)
        self.assertEqual(edges, [])
        self.assertIn("earlier", dropped[0])

    def test_drops_supersession_across_two_different_kinds(self):
        items = [prop("c", kind="claim", choice=""), prop("d", kind="decision")]
        edges, dropped = link.validate([{"kind": "supersedes", "from": "p2", "to": "p1"}], items)
        self.assertEqual(edges, [])
        self.assertIn("kind", dropped[0])

    def test_drops_supersession_when_either_date_is_missing(self):
        # 13 of the corpus's 372 documents resolve no date at all, and
        # supersession is the one relation that rests entirely on dates.
        items = [prop("old", date=None), prop("new", date="2026-06-01")]
        edges, dropped = link.validate([{"kind": "supersedes", "from": "p2", "to": "p1"}], items)
        self.assertEqual(edges, [])
        self.assertIn("date", dropped[0])

    def test_drops_supersession_between_records_sharing_a_date(self):
        items = [prop("a", date="2026-06-18"), prop("b", date="2026-06-18")]
        edges, dropped = link.validate([{"kind": "supersedes", "from": "p2", "to": "p1"}], items)
        self.assertEqual(edges, [])


class LedgerRuleTests(unittest.TestCase):
    """Rules docket/ledger.py enforces on append, mirrored here.

    An edge that passes validation and then aborts the append is worse than one
    dropped now: acceptance has no transaction, so the abort leaves records
    written and the stage untouched.
    """

    def test_drops_support_pointing_at_a_question(self):
        items = [prop("q", kind="question", choice=""), prop("d")]
        edges, dropped = link.validate(
            [{"kind": "supports", "from": "p2", "to": "p1"}], items)
        self.assertEqual(edges, [])
        self.assertIn("question", dropped[0])

    def test_keeps_support_pointing_at_a_claim(self):
        items = [prop("c", kind="claim", choice=""), prop("d")]
        edges, _ = link.validate(
            [{"kind": "supports", "from": "p2", "to": "p1"}], items)
        self.assertEqual(len(edges), 1)

    def test_drops_a_second_record_superseding_the_same_target(self):
        # The ledger retires a target once; the second append is refused.
        items = [prop("old", date="2026-01-01"),
                 prop("mid", date="2026-03-01"),
                 prop("new", date="2026-06-01")]
        edges, dropped = link.validate([
            {"kind": "supersedes", "from": "p2", "to": "p1"},
            {"kind": "supersedes", "from": "p3", "to": "p1"},
        ], items)
        self.assertEqual(len(edges), 1)
        self.assertTrue(any("already" in d for d in dropped))


class SupportsAcyclicTests(unittest.TestCase):
    def test_keeps_a_chain(self):
        items = [prop("a"), prop("b"), prop("c")]
        edges, dropped = link.validate([
            {"kind": "supports", "from": "p2", "to": "p1"},
            {"kind": "supports", "from": "p3", "to": "p2"},
        ], items)
        self.assertEqual(len(edges), 2)
        self.assertEqual(dropped, [])

    def test_drops_the_edge_that_closes_a_two_record_cycle(self):
        items = [prop("a"), prop("b")]
        edges, dropped = link.validate([
            {"kind": "supports", "from": "p2", "to": "p1"},
            {"kind": "supports", "from": "p1", "to": "p2"},
        ], items)
        self.assertEqual(len(edges), 1)
        self.assertIn("cycle", dropped[0])

    def test_drops_the_edge_that_closes_a_longer_cycle(self):
        items = [prop("a"), prop("b"), prop("c")]
        edges, dropped = link.validate([
            {"kind": "supports", "from": "p2", "to": "p1"},
            {"kind": "supports", "from": "p3", "to": "p2"},
            {"kind": "supports", "from": "p1", "to": "p3"},
        ], items)
        self.assertEqual(len(edges), 2)
        self.assertTrue(any("cycle" in d for d in dropped))

    def test_a_cycle_through_supersedes_does_not_block_a_supports_edge(self):
        # Only supports has to stay acyclic; the two relations are separate.
        items = [prop("a", date="2026-01-01"), prop("b", date="2026-06-01")]
        edges, _ = link.validate([
            {"kind": "supersedes", "from": "p2", "to": "p1"},
            {"kind": "supports", "from": "p2", "to": "p1"},
        ], items)
        self.assertEqual(len(edges), 2)


class ContradictionTests(unittest.TestCase):
    def pair(self):
        return [prop("a", kind="claim", choice="", text="Write-gating adds 50-200ms"),
                prop("b", kind="claim", choice="", text="Write latency target is under 50ms",
                     path="b.md")]

    def test_keeps_a_contradiction_between_two_records(self):
        edges, dropped = link.validate(
            [{"kind": "contradicts", "from": "p1", "to": "p2"}], self.pair())
        self.assertEqual(len(edges), 1)
        self.assertEqual(dropped, [])

    def test_a_contradiction_needs_no_date_and_no_shared_kind(self):
        items = [prop("a", kind="claim", choice="", date=None),
                 prop("b", kind="decision", path="b.md")]
        edges, dropped = link.validate(
            [{"kind": "contradicts", "from": "p1", "to": "p2"}], items)
        self.assertEqual(len(edges), 1)

    def test_a_contradiction_becomes_a_proposed_question(self):
        # The spec's rule: a contradiction the linker cannot resolve is a
        # question naming both records, never a silent supersedes.
        items = self.pair()
        edges = [{"kind": "contradicts", "from": "p1", "to": "p2"}]
        asked = link.questions(edges, items)
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0]["kind"], "question")

    def test_the_question_names_both_records(self):
        items = self.pair()
        asked = link.questions([{"kind": "contradicts", "from": "p1", "to": "p2"}], items)
        text = asked[0]["text"]
        self.assertIn("50-200ms", text)
        self.assertIn("under 50ms", text)

    def test_the_question_anchors_on_one_of_the_two_sources(self):
        # A synthesized record still needs a line a reviewer can open.
        items = self.pair()
        asked = link.questions([{"kind": "contradicts", "from": "p1", "to": "p2"}], items)
        self.assertIn(asked[0]["source"]["path"], {"a.md", "b.md"})
        self.assertTrue(asked[0]["anchor"])

    def test_the_same_contradiction_asks_the_same_question_twice_over(self):
        items = self.pair()
        edge = [{"kind": "contradicts", "from": "p1", "to": "p2"}]
        self.assertEqual(link.questions(edge, items)[0]["key"],
                         link.questions(edge, items)[0]["key"])

    def test_the_question_keys_apart_from_the_record_it_borrowed_from(self):
        # It takes that record's anchor and source. Keying the same would make
        # acceptance drop one of the two as a duplicate, silently.
        items = self.pair()
        asked = link.questions([{"kind": "contradicts", "from": "p1", "to": "p2"}], items)
        self.assertNotEqual(asked[0]["key"], items[0]["key"])
        self.assertNotEqual(asked[0]["key"], items[1]["key"])

    def test_a_contradiction_writes_no_relation_onto_either_record(self):
        items = self.pair()
        out = link.apply([{"kind": "contradicts", "from": "p1", "to": "p2"}], items)
        self.assertEqual(out[0]["supports"], [])
        self.assertEqual(out[0]["supersedes"], [])

    def test_no_contradictions_asks_nothing(self):
        self.assertEqual(link.questions([], self.pair()), [])


class BatchTests(unittest.TestCase):
    def items(self, n, per_doc=7):
        # Seven per document against a size of 120 divides unevenly, so a naive
        # slicer splits a document and fails. Five per document would divide
        # cleanly and let a slicer pass.
        return [prop(f"anchor {i}", path=f"doc{i // per_doc}.md") for i in range(n)]

    def test_a_small_set_is_one_batch(self):
        self.assertEqual(len(link.batches(self.items(10), size=120)), 1)

    def test_a_large_set_splits(self):
        self.assertEqual(len(link.batches(self.items(300), size=120)), 3)

    def test_every_record_lands_in_exactly_one_batch(self):
        items = self.items(300)
        keys = [p["key"] for batch in link.batches(items, size=120) for p in batch]
        self.assertEqual(sorted(keys), sorted(p["key"] for p in items))

    def test_a_document_is_not_split_across_batches_when_it_fits(self):
        # Records from one document are the likeliest to relate, so splitting a
        # document costs the edges the linker would most reliably find.
        batches = link.batches(self.items(300), size=120)
        self.assertGreater(len(batches), 1)
        where: dict[str, int] = {}
        for index, batch in enumerate(batches):
            for item in batch:
                path = item["source"]["path"]
                self.assertEqual(where.setdefault(path, index), index,
                                 f"{path} spans more than one batch")

    def test_batching_is_off_for_a_size_of_zero(self):
        self.assertEqual(len(link.batches(self.items(300), size=0)), 1)


class ApplyTests(unittest.TestCase):
    def test_writes_supports_onto_the_supporting_record(self):
        items = [prop("a"), prop("b")]
        edges = [{"kind": "supports", "from": "p2", "to": "p1"}]
        out = link.apply(edges, items)
        self.assertEqual(out[1]["supports"], [[items[0]["key"]]])

    def test_writes_supersedes_onto_the_later_record(self):
        items = [prop("a", date="2026-01-01"), prop("b", date="2026-06-01")]
        edges = [{"kind": "supersedes", "from": "p2", "to": "p1"}]
        out = link.apply(edges, items)
        self.assertEqual(out[1]["supersedes"], [items[0]["key"]])

    def test_leaves_an_unreferenced_record_alone(self):
        items = [prop("a"), prop("b")]
        out = link.apply([], items)
        self.assertEqual(out[0].get("supports", []), [])

    def test_keeps_several_grounds_as_separate_alternatives(self):
        # docket/ledger.py reads supports as a list of conjunctive sets, so one
        # set means "all of these are required". A linker sees two independent
        # grounds and cannot tell that; joining them claims more than it saw.
        items = [prop("a"), prop("b"), prop("c")]
        edges = [{"kind": "supports", "from": "p3", "to": "p1"},
                 {"kind": "supports", "from": "p3", "to": "p2"}]
        out = link.apply(edges, items)
        self.assertEqual(out[2]["supports"],
                         [[items[0]["key"]], [items[1]["key"]]])

    def test_does_not_mutate_the_records_it_was_given(self):
        items = [prop("a", date="2026-01-01"), prop("b", date="2026-06-01")]
        items[1]["supersedes"] = []
        before = items[1]["supersedes"]
        link.apply([{"kind": "supersedes", "from": "p2", "to": "p1"}], items)
        self.assertEqual(before, [])


if __name__ == "__main__":
    unittest.main()
