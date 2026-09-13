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
        edges, dropped = link.validate([{"kind": "contradicts", "from": "p1", "to": "p2"}], items)
        self.assertEqual(edges, [])
        self.assertIn("contradicts", dropped[0])


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

    def test_collects_several_supports_into_one_justification_set(self):
        items = [prop("a"), prop("b"), prop("c")]
        edges = [{"kind": "supports", "from": "p3", "to": "p1"},
                 {"kind": "supports", "from": "p3", "to": "p2"}]
        out = link.apply(edges, items)
        self.assertEqual(out[2]["supports"], [[items[0]["key"], items[1]["key"]]])


if __name__ == "__main__":
    unittest.main()
