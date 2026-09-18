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


if __name__ == "__main__":
    unittest.main()
