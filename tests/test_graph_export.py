import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from docket.graph_export import to_mermaid


def entry(ident, kind, text="t", **fields):
    base = {
        "id": ident,
        "kind": kind,
        "text": text,
        "supports": [],
        "depends_on": [],
        "answers": [],
        "supersedes": [],
        "retired_by": "",
    }
    base.update(fields)
    return base


class MermaidTests(unittest.TestCase):
    def test_an_unrelated_record_is_left_out(self):
        out = to_mermaid([entry("d1", "decision"), entry("c2", "claim")])
        self.assertEqual(out, "")

    def test_a_support_edge_points_at_the_record_it_holds_up(self):
        out = to_mermaid([entry("c1", "claim"), entry("d2", "decision", supports=[["c1"]])])
        self.assertIn("c1 --> d2", out)

    def test_each_relation_takes_its_own_arrow(self):
        records = [
            entry("q1", "question"),
            entry("c2", "claim"),
            entry("d3", "decision", supports=[["c2"]], answers=["q1"]),
            entry("d4", "decision", depends_on=["d3"], supersedes=["d3"]),
        ]
        out = to_mermaid(records, superseded=True)
        self.assertIn("c2 --> d3", out)
        self.assertIn("d3 ==> q1", out)
        self.assertIn("d4 -.-> d3", out)
        self.assertIn("d4 -- retires --> d3", out)

    def test_kind_picks_the_node_shape(self):
        records = [
            entry("q1", "question"),
            entry("c2", "claim"),
            entry("d3", "decision", supports=[["c2"]], answers=["q1"]),
        ]
        out = to_mermaid(records)
        self.assertIn('q1{{"q1', out)
        self.assertIn('c2(["c2', out)
        self.assertIn('d3["d3', out)

    def test_two_support_sets_get_a_join_node_each(self):
        # supports is a list of lists and each inner list is one complete
        # justification. Fanning both into the record directly would draw it
        # as needing every premise when it needs one set.
        records = [
            entry("c1", "claim"),
            entry("c2", "claim"),
            entry("d3", "decision", supports=[["c1"], ["c2"]]),
        ]
        out = to_mermaid(records)
        self.assertIn("c1 --> d3_set1", out)
        self.assertIn("d3_set1 --> d3", out)
        self.assertIn("c2 --> d3_set2", out)
        self.assertIn("d3_set2 --> d3", out)

    def test_one_support_set_gets_no_join_node(self):
        records = [
            entry("c1", "claim"),
            entry("c2", "claim"),
            entry("d3", "decision", supports=[["c1", "c2"]]),
        ]
        out = to_mermaid(records)
        self.assertNotIn("_set", out)
        self.assertIn("c1 --> d3", out)
        self.assertIn("c2 --> d3", out)

    def test_retired_records_are_dropped_by_default(self):
        records = [
            entry("c1", "claim", retired_by="c9"),
            entry("d2", "decision", supports=[["c1"]]),
        ]
        self.assertEqual(to_mermaid(records), "")

    def test_superseded_keeps_them_and_marks_them(self):
        records = [
            entry("c1", "claim", retired_by="c9"),
            entry("d2", "decision", supports=[["c1"]]),
        ]
        out = to_mermaid(records, superseded=True)
        self.assertIn("c1 --> d2", out)
        self.assertIn("classDef retired", out)
        self.assertIn("class c1 retired", out)

    def test_detail_zero_prints_ids_alone(self):
        records = [
            entry("c1", "claim", "a long proposition"),
            entry("d2", "decision", supports=[["c1"]]),
        ]
        out = to_mermaid(records, detail=0)
        self.assertIn('c1(["c1"])', out)

    def test_a_quote_in_the_text_cannot_break_the_node(self):
        records = [
            entry("c1", "claim", 'he said "no"'),
            entry("d2", "decision", supports=[["c1"]]),
        ]
        out = to_mermaid(records)
        self.assertNotIn('"he said "no""', out)
        self.assertIn("he said 'no'", out)

    def test_a_newline_in_the_text_stays_on_one_line(self):
        records = [
            entry("c1", "claim", "first\nsecond"),
            entry("d2", "decision", supports=[["c1"]]),
        ]
        out = to_mermaid(records)
        self.assertIn("first second", out)

    def test_direction_is_honoured(self):
        records = [entry("c1", "claim"), entry("d2", "decision", supports=[["c1"]])]
        self.assertTrue(to_mermaid(records, direction="TD").startswith("flowchart TD"))

    def test_an_edge_to_a_record_outside_the_selection_is_dropped(self):
        # graph --kind or --find can hand over a subset. An arrow to a record
        # that is not drawn renders as a bare node mermaid invents.
        records = [entry("d2", "decision", supports=[["c99"]], depends_on=["d98"])]
        self.assertEqual(to_mermaid(records), "")


if __name__ == "__main__":
    unittest.main()
