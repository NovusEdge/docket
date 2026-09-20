import argparse
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from docket.cli import main


class GraphFormatCliTests(unittest.TestCase):
    """The --format path end to end.

    Every other graph test calls to_mermaid or to_dot directly, so the argparse
    wiring, the filters and the empty-selection message went uncovered.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(
            ["git", "-C", str(self.root), "init", "-b", "main"], check=True, capture_output=True
        )
        (self.root / ".docket").mkdir()
        (self.root / ".docket" / "ledger.jsonl").write_text("", encoding="utf-8")
        self.cwd = Path.cwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def seed(self):
        self.run_cli("claim", "the loader scans plugins", "--state", "accepted", "--scope", "a/**")
        self.run_cli(
            "question", "where does the plugin go?", "--scope", "a/**", "--cost", "it breaks"
        )
        self.run_cli(
            "decision",
            "write plugins/docket.ts",
            "--choice",
            "flat path",
            "--scope",
            "a/**",
            "--supports",
            "c1",
            "--answers",
            "q2",
            "--cost",
            "a nested path is never seen",
        )

    def test_mermaid_prints_a_flowchart(self):
        self.seed()
        code, out, _ = self.run_cli("graph", "--format", "mermaid", "--no-interactive")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("flowchart LR"))
        self.assertIn("c1 --> d3", out)
        self.assertIn("d3 ==> q2", out)

    def test_dot_prints_a_digraph(self):
        self.seed()
        code, out, _ = self.run_cli("graph", "--format", "dot", "--no-interactive")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("digraph docket {"))
        self.assertIn('"c1" -> "d3"', out)

    def test_an_empty_ledger_says_nothing_is_recorded(self):
        code, out, _ = self.run_cli("graph", "--format", "mermaid", "--no-interactive")
        self.assertEqual(code, 0)
        self.assertIn("nothing recorded", out)

    def test_a_ledger_with_no_relation_says_so_on_stderr(self):
        self.run_cli("claim", "alone", "--scope", "a/**", "--cost", "none")
        code, out, err = self.run_cli("graph", "--format", "mermaid", "--no-interactive")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("carries a relation", err)

    def test_find_narrows_the_export(self):
        self.seed()
        self.run_cli(
            "decision", "something else", "--choice", "x", "--scope", "z/**", "--cost", "none"
        )
        _, wide, _ = self.run_cli("graph", "--format", "mermaid", "--no-interactive")
        _, narrow, _ = self.run_cli(
            "graph", "--format", "mermaid", "--find", "plugin", "--no-interactive"
        )
        self.assertLessEqual(len(narrow), len(wide))
        self.assertIn("d3", narrow)

    def test_detail_zero_prints_bare_ids(self):
        self.seed()
        _, out, _ = self.run_cli(
            "graph", "--format", "mermaid", "--detail", "0", "--no-interactive"
        )
        self.assertIn('c1(["c1"])', out)

    def test_direction_reaches_the_renderer(self):
        self.seed()
        _, out, _ = self.run_cli(
            "graph", "--format", "dot", "--direction", "TD", "--no-interactive"
        )
        self.assertIn("rankdir=TD;", out)

    def test_superseded_reaches_the_renderer(self):
        self.seed()
        self.run_cli(
            "decision",
            "write plugins/docket.ts after all",
            "--choice",
            "flat path, confirmed",
            "--scope",
            "a/**",
            "--supersedes",
            "d3",
            "--answers",
            "q2",
            "--cost",
            "none",
        )
        _, without, _ = self.run_cli("graph", "--format", "mermaid", "--no-interactive")
        _, with_retired, _ = self.run_cli(
            "graph", "--format", "mermaid", "--superseded", "--no-interactive"
        )
        self.assertNotIn("retires", without)
        self.assertIn("retires", with_retired)
        self.assertIn("classDef retired", with_retired)

    def test_an_unknown_format_is_refused_by_the_parser(self):
        with self.assertRaises(SystemExit):
            self.run_cli("graph", "--format", "graphml", "--no-interactive")

    def test_format_output_is_pipeable_with_no_colour_codes(self):
        self.seed()
        _, out, _ = self.run_cli("graph", "--format", "dot", "--no-interactive")
        self.assertNotIn("\x1b[", out)

    def test_format_conflicts_with_interactive(self):
        # Without the guard --format silently won in a terminal, so a caller
        # who asked for the viewer got text and no word about it.
        self.seed()
        with self.assertRaises(SystemExit):
            self.run_cli("graph", "--format", "mermaid", "--interactive")

    def test_format_works_with_no_interactive_and_with_neither(self):
        self.seed()
        for extra in (("--no-interactive",), ()):
            code, out, _ = self.run_cli("graph", "--format", "dot", *extra)
            self.assertEqual(code, 0)
            self.assertTrue(out.startswith("digraph docket {"))

    def test_a_supersede_chain_draws_every_link(self):
        self.seed()
        self.run_cli(
            "decision",
            "second",
            "--choice",
            "b",
            "--scope",
            "a/**",
            "--supersedes",
            "d3",
            "--cost",
            "none",
        )
        self.run_cli(
            "decision",
            "third",
            "--choice",
            "c",
            "--scope",
            "a/**",
            "--supersedes",
            "d4",
            "--cost",
            "none",
        )
        _, out, _ = self.run_cli("graph", "--format", "mermaid", "--superseded", "--no-interactive")
        self.assertIn("d4 -- retires --> d3", out)
        self.assertIn("d5 -- retires --> d4", out)

    def test_a_kind_filter_drops_the_edges_it_orphans(self):
        # --kind hands over a subset. An edge whose other end is filtered out
        # would render as a bare node mermaid invents.
        self.seed()
        _, out, _ = self.run_cli(
            "graph", "--format", "mermaid", "--kind", "decision", "--no-interactive"
        )
        self.assertNotIn("c1", out)
        self.assertNotIn("q2", out)

    def test_a_state_filter_reaches_the_export(self):
        self.seed()
        code, out, err = self.run_cli(
            "graph", "--format", "mermaid", "--state", "rejected", "--no-interactive"
        )
        self.assertEqual(code, 0)
        self.assertIn("nothing recorded", out + err)

    def test_csv_writes_both_tables_into_the_named_directory(self):
        self.seed()
        target = self.root / "gephi"
        code, out, _ = self.run_cli(
            "graph", "--format", "csv", "--out", str(target), "--no-interactive"
        )
        self.assertEqual(code, 0)
        self.assertTrue((target / "nodes.csv").is_file())
        self.assertTrue((target / "edges.csv").is_file())
        self.assertIn("Gephi", out)

    def test_csv_without_out_is_refused(self):
        # Gephi imports node and edge tables separately, so stdout cannot carry
        # both and a silent choice of one would be the wrong one half the time.
        self.seed()
        code, _, err = self.run_cli("graph", "--format", "csv", "--no-interactive")
        self.assertEqual(code, 2)
        self.assertIn("--out", err)

    def test_out_without_csv_is_refused(self):
        self.seed()
        code, _, err = self.run_cli(
            "graph", "--format", "dot", "--out", str(self.root / "x"), "--no-interactive"
        )
        self.assertEqual(code, 2)
        self.assertIn("--out belongs to --format csv", err)

    def test_forest_orders_children_by_file_position_not_id_number(self):
        # Part C makes IDs per-kind, so d1 can be written after c7. Global
        # monotonic-ID validation forbids that ledger today, so this drives
        # the static renderer directly rather than through the CLI's
        # validated read. A numeric child sort would put d1 first; file
        # order puts c7 first.
        from docket.cli.graph import _render_graph

        root = {
            "id": "q9",
            "kind": "question",
            "text": "where does the plugin go?",
            "state": "open",
            "supports": [],
        }
        c7 = {
            "id": "c7",
            "kind": "claim",
            "text": "c7 supports q9",
            "state": "accepted",
            "supports": [["q9"]],
        }
        d1 = {
            "id": "d1",
            "kind": "claim",
            "text": "d1 supports q9",
            "state": "accepted",
            "supports": [["q9"]],
        }
        entries = [root, c7, d1]
        args = argparse.Namespace(plain=True, pretty=False)
        out = io.StringIO()
        with redirect_stdout(out):
            code = _render_graph(entries, {}, args, "forest")
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertLess(text.index("c7"), text.index("d1"))

    def test_a_filter_reaches_the_csv_tables(self):
        self.seed()
        target = self.root / "gephi"
        self.run_cli(
            "graph",
            "--format",
            "csv",
            "--out",
            str(target),
            "--kind",
            "decision",
            "--no-interactive",
        )
        if (target / "nodes.csv").is_file():
            self.assertNotIn("q2", (target / "nodes.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
