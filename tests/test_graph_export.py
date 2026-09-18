import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from docket.graph_export import to_dot, to_mermaid


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


class DotTests(unittest.TestCase):
    def linked(self):
        return [
            entry("q1", "question"),
            entry("c2", "claim"),
            entry("d3", "decision", supports=[["c2"]], answers=["q1"]),
            entry("d4", "decision", depends_on=["d3"], supersedes=["d3"]),
        ]

    def test_it_opens_and_closes_a_digraph(self):
        out = to_dot(self.linked(), superseded=True)
        self.assertTrue(out.startswith("digraph docket {"))
        self.assertTrue(out.rstrip().endswith("}"))

    def test_each_relation_takes_its_own_style(self):
        out = to_dot(self.linked(), superseded=True)
        self.assertIn('"c2" -> "d3" [style=solid, arrowhead=normal]', out)
        self.assertIn('"d3" -> "q1" [style=bold, arrowhead=vee]', out)
        self.assertIn('"d4" -> "d3" [style=dashed, arrowhead=empty]', out)
        self.assertIn("retires", out)

    def test_kind_picks_the_node_shape(self):
        out = to_dot(self.linked(), superseded=True)
        self.assertIn('"q1" [shape=hexagon', out)
        self.assertIn('"c2" [shape=ellipse', out)
        self.assertIn('"d3" [shape=box', out)

    def test_a_quote_is_escaped_rather_than_replaced(self):
        # DOT takes a backslash escape, where mermaid needs the character gone.
        records = [
            entry("c1", "claim", 'he said "no"'),
            entry("d2", "decision", supports=[["c1"]]),
        ]
        out = to_dot(records)
        self.assertIn('he said \\"no\\"', out)

    def test_a_backslash_is_escaped_before_a_quote_is_added(self):
        # Escaping the quote first would leave the backslash unescaped and
        # turn the label into a DOT syntax error.
        records = [
            entry("c1", "claim", "a path C:\\temp"),
            entry("d2", "decision", supports=[["c1"]]),
        ]
        out = to_dot(records)
        self.assertIn("C:\\\\temp", out)

    def test_retired_records_are_filled_grey(self):
        records = [
            entry("c1", "claim", retired_by="c9"),
            entry("d2", "decision", supports=[["c1"]]),
        ]
        out = to_dot(records, superseded=True)
        self.assertIn("style=filled", out)
        self.assertIn("#f3f3f3", out)

    def test_two_support_sets_get_a_point_join_node_each(self):
        records = [
            entry("c1", "claim"),
            entry("c2", "claim"),
            entry("d3", "decision", supports=[["c1"], ["c2"]]),
        ]
        out = to_dot(records)
        self.assertIn('"d3_set1" [shape=point', out)
        self.assertIn('"c1" -> "d3_set1"', out)
        self.assertIn('"d3_set1" -> "d3"', out)

    def test_direction_is_honoured(self):
        records = [entry("c1", "claim"), entry("d2", "decision", supports=[["c1"]])]
        self.assertIn("rankdir=TD;", to_dot(records, direction="TD"))

    def test_an_unrelated_record_is_left_out(self):
        self.assertEqual(to_dot([entry("d1", "decision")]), "")

    def test_both_formats_draw_the_same_records(self):
        records = self.linked()
        for superseded in (False, True):
            dot = to_dot(records, superseded=superseded)
            mermaid = to_mermaid(records, superseded=superseded)
            for ident in ("q1", "c2", "d3", "d4"):
                self.assertEqual(
                    f'"{ident}" [' in dot,
                    f"  {ident}" in mermaid,
                    f"{ident} differs between formats at superseded={superseded}",
                )


@unittest.skipUnless(shutil.which("dot"), "graphviz is not installed")
class DotRendersTests(unittest.TestCase):
    """Hand the output to graphviz. Only a real parse catches a bad label."""

    def render(self, text):
        result = subprocess.run(
            ["dot", "-Tsvg"], input=text, capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<svg", result.stdout)
        return result.stdout

    def test_a_plain_graph_renders(self):
        records = [
            entry("q1", "question", "does the plugin load?"),
            entry("c2", "claim", "the loader scans plugins/"),
            entry("d3", "decision", "write plugins/docket.ts", supports=[["c2"]], answers=["q1"]),
            entry("d4", "decision", "keep the nested path", depends_on=["d3"], supersedes=["d3"]),
        ]
        self.render(to_dot(records, superseded=True))

    def test_hostile_label_text_renders(self):
        # A quote, a backslash, a newline and a brace each end the DOT label or
        # the statement when they reach graphviz unescaped.
        records = [
            entry("c1", "claim", 'he said "no" on C:\\temp\nand {then} left'),
            entry("d2", "decision", "a -> b [x]", supports=[["c1"]]),
        ]
        self.render(to_dot(records))

    def test_a_join_node_renders(self):
        records = [
            entry("c1", "claim"),
            entry("c2", "claim"),
            entry("d3", "decision", supports=[["c1"], ["c2"]]),
        ]
        self.render(to_dot(records))

    def test_this_project_s_own_ledger_renders(self):
        import docket.ledger as ledger

        path = Path(__file__).parent.parent / ".docket" / "ledger.jsonl"
        if not path.is_file():
            self.skipTest("no project ledger")
        entries = ledger.project(ledger.read(path), validated=True)
        svg = self.render(to_dot(entries, superseded=True))
        self.assertGreater(len(svg), 10_000)


@unittest.skipUnless(
    shutil.which("mmdc") and os.environ.get("DOCKET_TEST_MERMAID"),
    "set DOCKET_TEST_MERMAID=1 with mermaid-cli installed",
)
class MermaidRendersTests(unittest.TestCase):
    """Parse the mermaid output for real.

    Opt-in: mmdc drives a headless browser and takes seconds, which is too much
    to pay on every `just test`. CI sets DOCKET_TEST_MERMAID=1.
    """

    def render(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "g.mmd"
            target = Path(tmp) / "g.svg"
            source.write_text(text, encoding="utf-8")
            result = subprocess.run(
                ["mmdc", "-i", str(source), "-o", str(target)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target.is_file(), result.stderr)

    def test_hostile_label_text_parses(self):
        records = [
            entry("c1", "claim", 'he said "no" on C:\\temp and [then] {left}'),
            entry("d2", "decision", "a --> b; end", supports=[["c1"]]),
        ]
        self.render(to_mermaid(records))

    def test_this_project_s_own_ledger_parses(self):
        import docket.ledger as ledger

        path = Path(__file__).parent.parent / ".docket" / "ledger.jsonl"
        if not path.is_file():
            self.skipTest("no project ledger")
        entries = ledger.project(ledger.read(path), validated=True)
        self.render(to_mermaid(entries, superseded=True))


class FormatParityTests(unittest.TestCase):
    def records(self):
        return [
            entry("q1", "question"),
            entry("c2", "claim"),
            entry("c3", "claim"),
            entry("d4", "decision", supports=[["c2"], ["c3"]], answers=["q1"]),
            entry("d5", "decision", depends_on=["d4"], supersedes=["d4"]),
            entry("c6", "claim", retired_by="c9"),
        ]

    def test_both_formats_draw_the_same_edges(self):
        from docket.graph_export import _selected

        for superseded in (False, True):
            drawn, edges = _selected(self.records(), superseded=superseded)
            dot = to_dot(self.records(), superseded=superseded)
            mermaid = to_mermaid(self.records(), superseded=superseded)
            for source, target, _ in edges:
                self.assertIn(f'"{source}" -> "{target}"', dot)
                self.assertRegex(mermaid, rf"\n  {source} \S+ {target}$|\n  {source} .+ {target}\n")
            self.assertEqual(
                len(edges), dot.count(" -> "), f"dot edge count at superseded={superseded}"
            )

    def test_neither_format_emits_an_edge_to_an_undrawn_node(self):
        from docket.graph_export import _selected

        for superseded in (False, True):
            drawn, edges = _selected(self.records(), superseded=superseded)
            ids = {str(e["id"]) for e in drawn}
            for source, target, _ in edges:
                for end in (source, target):
                    self.assertTrue(end in ids or "_set" in end, f"{end} is not drawn")


class DetailBoundaryTests(unittest.TestCase):
    def pair(self, text):
        return [entry("c1", "claim", text), entry("d2", "decision", supports=[["c1"]])]

    def test_detail_one_does_not_produce_an_empty_or_broken_label(self):
        for render in (to_mermaid, to_dot):
            out = render(self.pair("a long proposition"), detail=1)
            self.assertIn("c1", out)

    def test_detail_past_the_text_length_leaves_it_whole(self):
        out = to_mermaid(self.pair("short"), detail=9999)
        self.assertIn("short", out)
        self.assertNotIn("…", out)

    def test_non_ascii_text_survives_both_formats(self):
        for render in (to_mermaid, to_dot):
            out = render(self.pair("größe and 日本語"), detail=40)
            self.assertIn("größe", out)

    def test_a_record_with_empty_text_falls_back_to_its_id(self):
        for render in (to_mermaid, to_dot):
            out = render(self.pair(""), detail=40)
            self.assertIn("c1", out)


if __name__ == "__main__":
    unittest.main()
