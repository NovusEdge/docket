"""Anchor matching and date resolution. No model, no network."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from docket.construct import extract


class AnchorMatchTests(unittest.TestCase):
    SOURCE = "\n".join(
        [
            "# Anti-Context-Pollution Architecture Decisions",
            "",
            "Date: 2026-06-18",
            "",
            "### 1. SAVER Audit-Repair: Tiered by Layer",
            "",
            "**Decision:** Option B - tiered checking by layer.",
            "",
            "**Rationale:** State contamination requires sanitization first.",
        ]
    )

    def test_finds_a_line_quoted_verbatim(self):
        self.assertEqual(
            extract.anchor_line("### 1. SAVER Audit-Repair: Tiered by Layer", self.SOURCE), 5
        )

    def test_finds_a_line_whose_emphasis_the_model_dropped(self):
        # The spike's entire batch-one miss: source has the bold markers, the
        # model's anchor does not.
        self.assertEqual(
            extract.anchor_line("Decision: Option B - tiered checking by layer.", self.SOURCE), 7
        )

    def test_finds_a_line_the_model_respaced(self):
        self.assertEqual(
            extract.anchor_line("Decision:   Option B - tiered   checking by layer.", self.SOURCE),
            7,
        )

    def test_returns_none_when_the_anchor_is_not_in_the_source(self):
        self.assertIsNone(extract.anchor_line("Decision: use JWT everywhere", self.SOURCE))

    def test_returns_the_first_match_when_a_line_repeats(self):
        source = "same line\nother\nsame line"
        self.assertEqual(extract.anchor_line("same line", source), 1)

    def test_an_empty_anchor_matches_nothing(self):
        self.assertIsNone(extract.anchor_line("", self.SOURCE))

    def test_does_not_match_a_line_that_merely_contains_the_anchor(self):
        # A substring match would let a three-word anchor claim any paragraph.
        source = "The decision to use JWT was taken after review"
        self.assertIsNone(extract.anchor_line("use JWT", source))


class MatchRateTests(unittest.TestCase):
    def test_reports_matched_over_total(self):
        source = "alpha\nbeta"
        proposals = [{"anchor": "alpha"}, {"anchor": "beta"}, {"anchor": "gamma"}]
        self.assertEqual(extract.match_rate(proposals, source), (2, 3))

    def test_an_empty_set_reports_zero_of_zero(self):
        self.assertEqual(extract.match_rate([], "alpha"), (0, 0))


class DateFromTextTests(unittest.TestCase):
    def test_reads_a_date_line_from_the_document_head(self):
        text = "# Title\n\nDate: 2026-06-18\nStatus: Decided\n"
        self.assertEqual(extract.date_from_text(text), "2026-06-18")

    def test_reads_a_bolded_date_label(self):
        text = "# Title\n\n**Date:** 2026-06-18\n"
        self.assertEqual(extract.date_from_text(text), "2026-06-18")

    def test_ignores_a_date_line_far_below_the_head(self):
        # A date deep in the body is a fact about the subject, not the document.
        text = "# Title\n" + "\n" * 40 + "Date: 2026-06-18\n"
        self.assertIsNone(extract.date_from_text(text))

    def test_returns_none_when_there_is_no_date_line(self):
        self.assertIsNone(extract.date_from_text("# Title\n\nSome prose.\n"))


class DateFromNameTests(unittest.TestCase):
    def test_reads_a_leading_date(self):
        self.assertEqual(extract.date_from_name("2026-06-18-coherence-layer.md"), "2026-06-18")

    def test_reads_a_date_sitting_mid_name(self):
        # positioning-2026-05-24.md in the real corpus; a leading-date parse
        # misses it entirely.
        self.assertEqual(extract.date_from_name("positioning-2026-05-24.md"), "2026-05-24")

    def test_returns_none_for_an_undated_name(self):
        self.assertIsNone(extract.date_from_name("silo-portability.md"))

    def test_rejects_an_impossible_date(self):
        self.assertIsNone(extract.date_from_name("2026-13-45-nonsense.md"))


class GitDatesTests(unittest.TestCase):
    def repo(self, tmp):
        root = Path(tmp)

        def run(*a):
            return subprocess.run(["git", "-C", str(root), *a], capture_output=True, check=True)

        run("init", "-q")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "t")
        (root / "a.md").write_text("alpha\n")
        (root / "b.md").write_text("beta\n")
        run("add", "-A")
        run("commit", "-q", "-m", "first", "--date", "2026-03-04T10:00:00+00:00")
        return root

    def test_maps_every_tracked_path_to_its_last_commit_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.repo(tmp)
            dates = extract.git_dates(root)
            self.assertEqual(dates["a.md"], "2026-03-04")
            self.assertEqual(dates["b.md"], "2026-03-04")

    def test_outside_a_repository_it_reports_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(extract.git_dates(Path(tmp)), {})

    def test_one_call_covers_the_whole_tree(self):
        # 133 of the real corpus's 372 documents have no date anywhere but git.
        # A subprocess per file would make the resolution pass the slow part.
        with tempfile.TemporaryDirectory() as tmp:
            root = self.repo(tmp)
            calls = []
            real = subprocess.run

            def counting(*a, **k):
                calls.append(a)
                return real(*a, **k)

            extract.subprocess.run = counting
            try:
                extract.git_dates(root)
            finally:
                extract.subprocess.run = real
            self.assertEqual(len(calls), 1)


class ResolveDateTests(unittest.TestCase):
    def test_a_date_line_wins_over_the_filename(self):
        self.assertEqual(
            extract.resolve_date("2026-01-01-thing.md", "Date: 2026-06-18\n", {}), "2026-06-18"
        )

    def test_the_filename_wins_over_git(self):
        self.assertEqual(
            extract.resolve_date(
                "2026-01-01-thing.md", "no date here", {"2026-01-01-thing.md": "2026-09-09"}
            ),
            "2026-01-01",
        )

    def test_git_answers_when_nothing_else_does(self):
        self.assertEqual(
            extract.resolve_date("thing.md", "no date here", {"thing.md": "2026-09-09"}),
            "2026-09-09",
        )

    def test_a_document_with_no_date_anywhere_resolves_to_none(self):
        # Pass 2 proposes no supersession edge for such a record.
        self.assertIsNone(extract.resolve_date("thing.md", "no date here", {}))


if __name__ == "__main__":
    unittest.main()
