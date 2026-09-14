"""The construct subcommand. Only the paths that need no model."""

import argparse
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from docket.cli import construct as cli_construct
from docket.construct import schema, stage
from docket.ledger import read


def prop(anchor, path="context/a.md", confidence="low", scope=None, text="Question?"):
    return schema.proposal(kind="decision", text=text, choice="yes", anchor=anchor,
                           rationale="because", scope=scope or [], confidence=confidence,
                           source={"path": path, "date": "2026-06-18"})


def args(**over):
    fields = {"paths": [], "review": False, "accept": False, "source": None,
              "jobs": 4, "dry_run": False, "exclude": [], "no_exclude": False,
              "untracked": False}
    fields.update(over)
    return argparse.Namespace(**fields)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.staged = Path(self.tmp.name) / "proposed.jsonl"

    def review(self, items):
        stage.write(self.staged, items)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli_construct.review(self.staged, live=set())
        return rc, out.getvalue()

    def test_says_so_when_nothing_is_staged(self):
        rc, out = self.review([])
        self.assertEqual(rc, 0)
        self.assertIn("nothing staged", out)

    def test_prints_the_source_document_as_a_heading(self):
        rc, out = self.review([prop("one")])
        self.assertIn("context/a.md", out)

    def test_prints_the_anchor_so_a_reader_can_find_the_line(self):
        rc, out = self.review([prop("**Decision:** keep it")])
        self.assertIn("**Decision:** keep it", out)

    def test_prints_the_record_text(self):
        rc, out = self.review([prop("one", text="Where does it live?")])
        self.assertIn("Where does it live?", out)

    def test_marks_a_record_whose_scope_resolves_to_nothing(self):
        rc, out = self.review([prop("one", scope=["gone/x.py"])])
        self.assertIn("unresolved", out)

    def test_reports_the_resolution_rate(self):
        rc, out = self.review([prop("one", scope=["gone/x.py"])])
        self.assertIn("0/1", out)


class AcceptDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.staged = Path(self.tmp.name) / "proposed.jsonl"
        self.ledger = Path(self.tmp.name) / "ledger.jsonl"

    def run_accept(self, items, **over):
        stage.write(self.staged, items)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli_construct.accept_staged(self.staged, self.ledger, **over)
        return rc, out.getvalue()

    def test_writes_accepted_records_and_reports_the_count(self):
        item = prop("one")
        item["state"] = "accepted"
        rc, out = self.run_accept([item])
        self.assertEqual(rc, 0)
        self.assertEqual(len(read(self.ledger)), 1)
        self.assertIn("1", out)

    def test_a_second_run_is_a_no_op(self):
        item = prop("one")
        item["state"] = "accepted"
        self.run_accept([item])
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli_construct.accept_staged(self.staged, self.ledger)
        self.assertEqual(rc, 0)
        self.assertEqual(len(read(self.ledger)), 1)

    def test_says_so_when_nothing_is_accepted_yet(self):
        rc, out = self.run_accept([prop("one")])
        self.assertEqual(rc, 0)
        self.assertIn("nothing accepted", out)


class FlagTests(unittest.TestCase):
    def test_review_and_accept_together_are_refused(self):
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli_construct.cmd_construct(args(review=True, accept=True))
        self.assertEqual(rc, 2)
        self.assertIn("--review", err.getvalue())

    def test_paths_with_accept_are_refused(self):
        # Extraction and acceptance are separate steps by design; running both
        # in one command would accept records nobody has read.
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli_construct.cmd_construct(args(paths=["context/"], accept=True))
        self.assertEqual(rc, 2)

    def test_no_paths_and_no_flag_is_refused(self):
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli_construct.cmd_construct(args())
        self.assertEqual(rc, 2)


class StagedPathTests(unittest.TestCase):
    def test_stages_in_the_project_when_it_has_a_docket_directory(self):
        # Construct's main case is a project whose ledger is absent, where
        # ledger_path() answers with the global store. Staging proposals there
        # puts them somewhere the user never looks.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / ".docket").mkdir()
            original = cli_construct.env.project_root
            try:
                cli_construct.env.project_root = lambda start=None: root
                self.assertEqual(cli_construct._staged_path(),
                                 root / ".docket" / "proposed.jsonl")
            finally:
                cli_construct.env.project_root = original

    def test_falls_back_to_the_ledger_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "global" / "ledger.jsonl"
            ledger.parent.mkdir(parents=True)
            originals = (cli_construct.env.project_root, cli_construct.env.ledger_path)
            try:
                cli_construct.env.project_root = lambda start=None: root
                cli_construct.env.ledger_path = lambda start=None: ledger
                self.assertEqual(cli_construct._staged_path(),
                                 ledger.parent / "proposed.jsonl")
            finally:
                (cli_construct.env.project_root,
                 cli_construct.env.ledger_path) = originals


class LedgerPairingTests(unittest.TestCase):
    def test_accept_writes_beside_the_staging_file(self):
        # Staging prefers a project's own .docket; acceptance must target the
        # same project, never the global store. Splitting them puts proposals
        # in one place and the records they became in another.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / ".docket").mkdir()
            original = cli_construct.env.project_root
            try:
                cli_construct.env.project_root = lambda start=None: root
                self.assertEqual(cli_construct._ledger_path().parent,
                                 cli_construct._staged_path().parent)
            finally:
                cli_construct.env.project_root = original


class MalformedStageTests(unittest.TestCase):
    """Hand-editing the stage is the documented workflow, so a bad edit has to
    report itself instead of raising a traceback."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.staged = Path(self.tmp.name) / "proposed.jsonl"

    def test_a_broken_line_names_the_file_and_the_line(self):
        self.staged.write_text(
            '{"key": "a", "state": "staged", "kind": "claim"}\nnot json\n')
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli_construct.review(self.staged, live=set())
        self.assertEqual(rc, 1)
        self.assertIn("line 2", err.getvalue())

    def test_a_record_missing_its_state_is_reported(self):
        self.staged.write_text('{"key": "a", "kind": "claim"}\n')
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli_construct.review(self.staged, live=set())
        self.assertEqual(rc, 1)
        self.assertIn("state", err.getvalue())


class ReviewSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.staged = Path(self.tmp.name) / "proposed.jsonl"

    def test_strips_control_characters_from_model_text(self):
        # Everything in a proposal came from a model. An escape sequence would
        # otherwise reach the terminal verbatim.
        item = prop("one", text="red \x1b[31mALERT\x1b[0m here")
        stage.write(self.staged, [item])
        out = io.StringIO()
        with redirect_stdout(out):
            cli_construct.review(self.staged, live=set())
        self.assertNotIn("\x1b", out.getvalue())
        self.assertIn("ALERT", out.getvalue())

    def test_truncates_text_too_long_to_read(self):
        item = prop("one", text="x" * 5000)
        stage.write(self.staged, [item])
        out = io.StringIO()
        with redirect_stdout(out):
            cli_construct.review(self.staged, live=set())
        self.assertLess(len(out.getvalue()), 3000)


class DryRunTests(unittest.TestCase):
    def test_dry_run_needs_no_sdk(self):
        # It reads no document and issues no call, so demanding the dependency
        # would refuse the one command someone runs to see what would happen.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.md").write_text("# a\n")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = cli_construct.cmd_construct(args(paths=[tmp], dry_run=True))
            self.assertEqual(rc, 0)
            self.assertNotIn("pip install", err.getvalue())
            self.assertIn("1 document", out.getvalue())


class DependencyTests(unittest.TestCase):
    def test_a_missing_sdk_names_the_install_command(self):
        # Every other command, and the SessionStart hook, keep working on a
        # machine that never installs it.
        message = cli_construct.MISSING_SDK
        self.assertIn("pip install", message)
        self.assertIn("openai", message)

    def test_importing_the_command_module_does_not_import_the_sdk(self):
        self.assertNotIn("openai", sys.modules)


if __name__ == "__main__":
    unittest.main()
