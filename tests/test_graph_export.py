import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from docket.graph_export import to_csv, to_dot, to_mermaid


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
        out = to_mermaid(records)
        self.assertNotIn("c1", out)
        self.assertIn('d2["d2', out)

    def test_a_record_that_retired_another_is_still_drawn(self):
        records = [
            entry("d1", "decision", retired_by="d2"),
            entry("d2", "decision", supersedes=["d1"]),
        ]
        out = to_mermaid(records)
        self.assertIn('d2["d2', out)
        self.assertNotIn("d1", out)

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
            entry("d3", "decision", supports=[["c2"]], answers=["q1"], retired_by="d4"),
            entry("d4", "decision", depends_on=["d3"], supersedes=["d3"]),
        ]

    def test_nodes_and_edges_carry_classes_for_the_web_view(self):
        out = to_dot(self.linked(), superseded=True)
        self.assertIn('"c2" [shape=ellipse, label="c2\\nt", class="claim"]', out)
        self.assertIn('class="decision retired"', out)
        self.assertIn('"c2" -> "d3" [style=solid, arrowhead=normal, class="supports"]', out)
        self.assertIn('class="retires"', out)

    def test_join_nodes_carry_the_join_class(self):
        records = [
            entry("c1", "claim"),
            entry("c2", "claim"),
            entry("d3", "decision", supports=[["c1"], ["c2"]]),
        ]
        self.assertIn('class="join"', to_dot(records))

    def test_the_graph_packs_its_components(self):
        self.assertIn('pack=true; packmode="array_u";', to_dot(self.linked(), superseded=True))

    def test_it_opens_and_closes_a_digraph(self):
        out = to_dot(self.linked(), superseded=True)
        self.assertTrue(out.startswith("digraph docket {"))
        self.assertTrue(out.rstrip().endswith("}"))

    def test_each_relation_takes_its_own_style(self):
        out = to_dot(self.linked(), superseded=True)
        self.assertIn('"c2" -> "d3" [style=solid, arrowhead=normal, class="supports"]', out)
        self.assertIn('"d3" -> "q1" [style=bold, arrowhead=vee, class="answers"]', out)
        self.assertIn('"d4" -> "d3" [style=dashed, arrowhead=empty, class="depends_on"]', out)
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

    def test_orphans_draws_unrelated_records_but_not_retired_ones(self):
        records = [
            entry("d1", "decision"),
            entry("c2", "claim", retired_by="c3"),
            entry("c3", "claim", supersedes=["c2"]),
        ]
        out = to_dot(records, orphans=True)
        self.assertIn('"d1" [', out)
        self.assertIn('"c3" [', out)
        self.assertNotIn('"c2" [', out)

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


def layout_records():
    return [
        entry("q1", "question", scope=["docs/a/x.md"]),
        entry("c2", "claim", scope=["docs/a/y.md"]),
        entry(
            "d3", "decision", state="adopted", supports=[["c2"]], answers=["q1"], scope=["src/*.py"]
        ),
        entry("d4", "decision", state="adopted", depends_on=["d3"]),
        entry("c5", "claim", supports=[["d4"]]),
        entry("c6", "claim", supports=[["c5"]], retired_by="c7"),
        entry("d7", "decision", depends_on=["c6"]),
    ]


def nested_records():
    # docs/ holds d3 and has two child boxes, so the emitters recurse past depth 1.
    return [
        entry("q1", "question", scope=["docs/a/x.md"]),
        entry("c2", "claim", scope=["docs/b/y.md"]),
        entry("d3", "decision", supports=[["c2"]], answers=["q1"], scope=["docs/z.md"]),
        entry("d4", "decision", depends_on=["d3"], scope=["src/*.py"]),
        entry("c5", "claim", supports=[["d4"]]),
    ]


class DotLayoutTests(unittest.TestCase):
    def test_nested_scope_boxes_nest_with_unique_cluster_ids(self):
        out = to_dot(nested_records(), group="scope")
        ids = [ln.split()[1] for ln in out.splitlines() if ln.strip().startswith("subgraph ")]
        self.assertEqual(ids, ["cluster_0", "cluster_1", "cluster_2", "cluster_3"])
        stack, where = [], {}
        for ln in out.splitlines():
            text = ln.strip()
            if text.startswith("subgraph "):
                stack.append(None)
            elif text.startswith("label=") and None in stack:
                stack[stack.index(None)] = text.split('label="')[1].split('"')[0]
            elif text == "}" and ln != "}":
                stack.pop()
            elif text.startswith('"') and "[" in text and "->" not in text:
                where[text.split('"')[1]] = list(stack)
        self.assertEqual(where["d3"], ["docs/"])
        self.assertEqual(where["q1"], ["docs/", "a/"])
        self.assertEqual(where["c2"], ["docs/", "b/"])
        self.assertEqual(where["d4"], ["src/"])
        self.assertEqual(where["c5"], [])

    def test_unconnected_records_in_a_box_are_laid_out_in_rows(self):
        records = [entry(f"d{i}", "decision") for i in range(1, 6)]
        records += [entry("c9", "claim"), entry("d8", "decision", supports=[["c9"]])]
        out = to_dot(records, group="kind", orphans=True)
        grid = [ln.strip() for ln in out.splitlines() if "style=invis" in ln]
        # Five records, rows of three: d1 d2 d3 / d4 d5. d8 has an edge and stays out.
        self.assertEqual(
            grid,
            [
                '"d1" -> "d2" [style=invis];',
                '"d2" -> "d3" [style=invis];',
                '"d4" -> "d5" [style=invis];',
            ],
        )
        self.assertNotIn("style=invis", to_dot(records, orphans=True))

    def test_group_kind_emits_a_cluster_per_kind(self):
        out = to_dot(layout_records(), group="kind")
        self.assertEqual(out.count("subgraph cluster_"), 3)
        for label in ("claims", "decisions", "questions"):
            self.assertIn(f'label="{label}"; class="group"; labeljust=l;', out)
        self.assertIn('fontname="monospace"; fontsize=18; margin=14;', out)

    def test_group_scope_nests_and_leaves_scopeless_records_outside(self):
        out = to_dot(layout_records(), group="scope")
        self.assertIn('label="docs/a/"', out)
        self.assertIn('label="src/"', out)
        lines = out.splitlines()
        node = next(i for i, ln in enumerate(lines) if ln.strip().startswith('"c2" ['))
        opener = max(i for i in range(node) if lines[i].strip().startswith("subgraph cluster_"))
        closer = next(i for i in range(opener + 1, len(lines)) if lines[i] == "  }")
        self.assertLess(node, closer)
        self.assertGreater(out.index('  "d4" ['), out.rindex("  }"))

    def test_an_unknown_group_is_refused(self):
        with self.assertRaises(ValueError):
            to_dot(layout_records(), group="dir")
        with self.assertRaises(ValueError):
            to_mermaid(layout_records(), group="dir")

    def test_focus_draws_only_the_neighbourhood_and_marks_the_focus_node(self):
        out = to_dot(layout_records(), focus="d3", hops=1)
        for ident in ("q1", "c2", "d3", "d4"):
            self.assertIn(f'"{ident}" [', out)
        for ident in ("c5", "d7"):
            self.assertNotIn(f'"{ident}"', out)
        (line,) = [ln for ln in out.splitlines() if ln.strip().startswith('"d3" [')]
        self.assertIn('class="decision adopted focus"', line)
        self.assertIn("penwidth=2.5", line)
        self.assertNotIn("penwidth", [ln for ln in out.splitlines() if '"c2" [' in ln][0])

    def test_an_unknown_focus_raises(self):
        with self.assertRaisesRegex(ValueError, "nope is not in this selection"):
            to_dot(layout_records(), focus="nope")

    def test_a_focused_record_with_no_relation_is_drawn_alone(self):
        records = [*layout_records(), entry("c99", "claim", "alone")]
        out = to_dot(records, focus="c99")
        (line,) = [ln for ln in out.splitlines() if ln.strip().startswith('"c99" [')]
        self.assertIn("focus", line)
        self.assertIn("penwidth=2.5", line)
        self.assertNotIn('"d3"', out)
        self.assertNotIn("->", out)
        flow = to_mermaid(records, focus="c99")
        self.assertIn("c99", flow)
        self.assertNotIn("d3", flow)

    def test_a_retired_record_is_outside_the_focus_unless_superseded(self):
        out = to_dot(layout_records(), focus="c5", hops=2)
        self.assertNotIn('"c6"', out)
        out = to_dot(layout_records(), focus="c5", hops=2, superseded=True)
        self.assertIn('"c6" [', out)

    def test_focus_keeps_a_join_whose_ends_survive_and_drops_a_cut_one(self):
        records = [
            entry("c1", "claim"),
            entry("c2", "claim"),
            entry("d3", "decision", supports=[["c1"], ["c2"]]),
            entry("d4", "decision", depends_on=["d3"]),
        ]
        out = to_dot(records, focus="d3", hops=1)
        self.assertEqual(out.count('class="join"'), 2)
        far = to_dot(records, focus="d4", hops=1)
        self.assertNotIn("_set", far)

    def test_focus_applies_before_grouping(self):
        out = to_dot(layout_records(), group="kind", focus="d3", hops=1)
        self.assertEqual(out.count("subgraph cluster_"), 3)
        out = to_dot(layout_records(), group="kind", focus="q1", hops=1)
        self.assertEqual(out.count("subgraph cluster_"), 2)


class MermaidLayoutTests(unittest.TestCase):
    def test_group_scope_emits_unique_quoted_subgraphs(self):
        out = to_mermaid(layout_records(), group="scope")
        self.assertIn('subgraph g_0 ["docs/a/"]', out)
        self.assertEqual(out.count("subgraph "), out.count("\n  end") + out.count("\n    end"))
        ids = [ln.split()[1] for ln in out.splitlines() if ln.strip().startswith("subgraph ")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_nested_scope_subgraphs_nest_and_balance(self):
        lines = to_mermaid(nested_records(), group="scope").splitlines()
        stack, where, ids = [], {}, []
        for ln in lines:
            text = ln.strip()
            if text.startswith("subgraph "):
                ids.append(text.split()[1])
                stack.append(text.split('["')[1].rstrip('"]'))
            elif text == "end":
                stack.pop()
            elif text[:2] in ("q1", "c2", "d3", "d4", "c5") and "-" not in text and "=" not in text:
                where[text[:2]] = list(stack)
        self.assertEqual(stack, [])
        self.assertEqual(ids, ["g_0", "g_1", "g_2", "g_3"])
        self.assertEqual(where["q1"], ["docs/", "a/"])
        self.assertEqual(where["c2"], ["docs/", "b/"])
        self.assertEqual(where["d3"], ["docs/"])
        self.assertEqual(where["c5"], [])

    def test_focus_selects_the_same_records_as_dot(self):
        out = to_mermaid(layout_records(), focus="d3", hops=1)
        self.assertIn("d4", out)
        self.assertNotIn("c5", out)


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

    def test_grouped_by_scope_renders_with_group_clusters(self):
        svg = self.render(to_dot(layout_records(), group="scope"))
        self.assertIn("group", svg)
        self.assertIn("docs/a/", svg)

    def test_nested_scope_boxes_render(self):
        svg = self.render(to_dot(nested_records(), group="scope"))
        self.assertEqual(svg.count('class="cluster group"'), 4)

    def test_a_focused_graph_renders(self):
        svg = self.render(to_dot(layout_records(), group="kind", focus="d3", hops=1))
        self.assertNotIn(">c5", svg)

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

    def test_nested_scope_subgraphs_parse(self):
        self.render(to_mermaid(nested_records(), group="scope"))
        self.render(to_mermaid(layout_records(), group="kind", focus="d3", hops=1))

    def test_this_project_s_own_ledger_parses(self):
        import docket.ledger as ledger

        path = Path(__file__).parent.parent / ".docket" / "ledger.jsonl"
        if not path.is_file():
            self.skipTest("no project ledger")
        entries = ledger.project(ledger.read(path), validated=True)
        self.render(to_mermaid(entries, superseded=True))


class SupportMarkTests(unittest.TestCase):
    def records(self):
        return [
            entry("c1", "claim", state="accepted", support="clean"),
            entry("c2", "claim", state="accepted", support="flagged", supports=[["c1"]]),
            entry("d3", "decision", state="adopted", support="unsupported", supports=[["c2"]]),
            entry("c4", "claim", state="unassessed", support="flagged", supports=[["c1"]]),
        ]

    def test_mermaid_dashes_the_border_by_status(self):
        out = to_mermaid(self.records())
        self.assertIn("class c2 flagged", out)
        self.assertIn("class d3 unsupported", out)
        # Only accepted and adopted records show support status to a reader.
        self.assertNotIn("c4 flagged", out)
        self.assertNotIn("c1 flagged", out)

    def test_dot_dashes_or_dots_the_border(self):
        out = to_dot(self.records())
        self.assertIn(
            '"c2" [shape=ellipse, label="c2\\nt", style=dashed, class="claim accepted flagged"]',
            out,
        )
        self.assertIn(
            '"d3" [shape=box, label="d3\\nt", style=dotted, class="decision adopted unsupported"]',
            out,
        )
        self.assertNotIn('"c1" [shape=ellipse, label="c1\\nt", style=', out)

    def test_dot_classes_carry_state_and_support_mark(self):
        out = to_dot(self.records())
        self.assertIn('class="claim accepted flagged"', out)
        self.assertIn('class="decision adopted unsupported"', out)

    def test_a_retired_record_keeps_its_grey_fill_and_no_mark(self):
        records = [
            entry("c1", "claim", state="accepted", support="flagged", retired_by="c9"),
            entry("d2", "decision", supports=[["c1"]]),
        ]
        self.assertNotIn("dashed", to_dot(records, superseded=True).split("->")[0])
        self.assertNotIn("class c1 flagged", to_mermaid(records, superseded=True))

    def test_csv_carries_a_support_column(self):
        import csv
        import io

        nodes, _ = to_csv(self.records())
        rows = {row["Id"]: row for row in csv.DictReader(io.StringIO(nodes))}
        self.assertEqual(rows["c2"]["support"], "flagged")
        self.assertEqual(rows["d3"]["support"], "unsupported")
        self.assertEqual(rows["c1"]["support"], "")


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


class CsvTests(unittest.TestCase):
    """The Gephi tables. Parsed with csv.reader, never by splitting on commas."""

    def rows(self, text):
        import csv
        import io

        return list(csv.reader(io.StringIO(text)))

    def graph(self):
        return [
            entry("c1", "claim", "a premise", state="accepted", scope=["a/**"]),
            entry("q2", "question", "which one?", state="open"),
            entry("d3", "decision", "pick it", state="adopted", supports=[["c1"]], answers=["q2"]),
        ]

    def test_the_node_table_carries_the_columns_gephi_recognises(self):
        nodes, _ = to_csv(self.graph())
        header, *body = self.rows(nodes)
        self.assertEqual(header[:2], ["Id", "Label"])
        self.assertEqual(sorted(row[0] for row in body), ["c1", "d3", "q2"])

    def test_the_edge_table_names_source_target_and_the_relation(self):
        _, edges = to_csv(self.graph())
        header, *body = self.rows(edges)
        self.assertEqual(header, ["Source", "Target", "Type", "Label", "Weight"])
        self.assertIn(["c1", "d3", "Directed", "supports", "1"], body)
        self.assertIn(["d3", "q2", "Directed", "answers", "1"], body)

    def test_every_edge_endpoint_appears_in_the_node_table(self):
        # Gephi creates a bare node for an unknown endpoint, which lands in the
        # layout with no kind and no label and looks like a real record.
        nodes, edges = to_csv(self.graph())
        known = {row[0] for row in self.rows(nodes)[1:]}
        for source, target, *_ in self.rows(edges)[1:]:
            self.assertIn(source, known)
            self.assertIn(target, known)

    def test_a_comma_in_the_text_does_not_split_a_column(self):
        nodes, _ = to_csv(
            [
                entry("c1", "claim", 'a premise, with a comma and a "quote"', state="accepted"),
                entry("d2", "decision", "x", supports=[["c1"]]),
            ],
            detail=0,
        )
        rows = self.rows(nodes)
        self.assertTrue(all(len(row) == len(rows[0]) for row in rows))
        text = rows[0].index("text")
        self.assertIn('a premise, with a comma and a "quote"', [row[text] for row in rows])

    def test_a_join_node_is_labelled_as_a_set(self):
        nodes, edges = to_csv(
            [
                entry("c1", "claim", "one", state="accepted"),
                entry("c2", "claim", "two", state="accepted"),
                entry("d3", "decision", "either", supports=[["c1"], ["c2"]]),
            ]
        )
        kinds = {row[0]: row[2] for row in self.rows(nodes)[1:]}
        joins = [ident for ident, kind in kinds.items() if kind == "set"]
        self.assertEqual(len(joins), 2)
        endpoints = {end for row in self.rows(edges)[1:] for end in row[:2]}
        self.assertTrue(set(joins) <= endpoints)

    def test_a_retired_record_is_flagged_and_only_appears_when_asked(self):
        records = [
            entry("c1", "claim", "old", state="accepted", retired_by="c9"),
            entry("d2", "decision", "x", supports=[["c1"]]),
        ]
        nodes, _ = to_csv(records)
        self.assertNotIn("c1", [row[0] for row in self.rows(nodes)[1:]])
        nodes, _ = to_csv(records, superseded=True)
        flags = {row[0]: row[4] for row in self.rows(nodes)[1:]}
        self.assertEqual(flags["c1"], "true")
        self.assertEqual(flags["d2"], "false")

    def test_focus_narrows_the_node_table(self):
        nodes, edges = to_csv(layout_records(), focus="d3", hops=1)
        self.assertEqual(sorted(row[0] for row in self.rows(nodes)[1:]), ["c2", "d3", "d4", "q1"])
        self.assertNotIn("c5", edges)
        with self.assertRaises(ValueError):
            to_csv(layout_records(), focus="nope")

    def test_focus_on_a_record_with_no_relation_lists_it_alone(self):
        records = [*layout_records(), entry("c99", "claim", "alone")]
        nodes, edges = to_csv(records, focus="c99")
        self.assertEqual([row[0] for row in self.rows(nodes)[1:]], ["c99"])
        self.assertEqual(self.rows(edges)[1:], [])

    def test_a_selection_with_no_relation_returns_two_empty_documents(self):
        self.assertEqual(to_csv([entry("c1", "claim", "alone")]), ("", ""))


if __name__ == "__main__":
    unittest.main()
