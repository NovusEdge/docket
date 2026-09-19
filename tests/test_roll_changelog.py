import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.roll_changelog import ChangelogError, roll

BASE = "https://github.com/NovusEdge/docket/compare/"

FULL = f"""# Changelog

## [Unreleased]

### Added

- A thing.

## [0.16.0] - 2026-09-19

### Added

- An older thing.

[Unreleased]: {BASE}v0.16.0...HEAD
[0.16.0]: {BASE}v0.15.0...v0.16.0
"""

EMPTY = f"""# Changelog

## [Unreleased]

## [0.16.0] - 2026-09-19

### Added

- An older thing.

[Unreleased]: {BASE}v0.16.0...HEAD
[0.16.0]: {BASE}v0.15.0...v0.16.0
"""


class RollTests(unittest.TestCase):
    def test_the_entry_moves_under_a_dated_version_heading(self):
        out = roll(FULL, "0.17.0", "2026-09-20")
        self.assertIn("## [0.17.0] - 2026-09-20", out)
        self.assertLess(out.index("## [0.17.0]"), out.index("- A thing."))
        self.assertLess(out.index("- A thing."), out.index("## [0.16.0]"))

    def test_a_fresh_unreleased_heading_is_left_behind(self):
        out = roll(FULL, "0.17.0", "2026-09-20")
        head, _, rest = out.partition("## [Unreleased]")
        self.assertTrue(head.strip().endswith("# Changelog"))
        self.assertTrue(rest.lstrip().startswith("## [0.17.0]"))

    def test_the_new_heading_is_spaced_like_every_other_one(self):
        # The captured section opens with the blank line that followed the
        # Unreleased heading, so 0.17.1 rolled with two blank lines under it.
        out = roll(FULL, "0.17.0", "2026-09-20")
        self.assertIn("## [0.17.0] - 2026-09-20\n\n### Added\n", out)
        self.assertNotIn("\n\n\n", out)

    def test_the_compare_links_move_with_it(self):
        out = roll(FULL, "0.17.0", "2026-09-20")
        self.assertIn(f"[Unreleased]: {BASE}v0.17.0...HEAD", out)
        self.assertIn(f"[0.17.0]: {BASE}v0.16.0...v0.17.0", out)
        self.assertIn(f"[0.16.0]: {BASE}v0.15.0...v0.16.0", out)

    def test_an_empty_unreleased_section_refuses_the_release(self):
        # 0.13.0 shipped with its entry still under Unreleased and nothing
        # reported it. This is the half of the fix that matters.
        with self.assertRaisesRegex(ChangelogError, "is empty"):
            roll(EMPTY, "0.17.0", "2026-09-20")

    def test_a_version_that_already_has_a_section_is_refused(self):
        with self.assertRaisesRegex(ChangelogError, "already has a section"):
            roll(FULL, "0.16.0", "2026-09-20")

    def test_a_changelog_with_no_unreleased_heading_is_refused(self):
        with self.assertRaisesRegex(ChangelogError, "no ## \\[Unreleased\\]"):
            roll("# Changelog\n\n## [0.16.0] - 2026-09-19\n", "0.17.0", "2026-09-20")

    def test_a_missing_compare_link_is_refused(self):
        text = FULL.replace(f"[Unreleased]: {BASE}v0.16.0...HEAD\n", "")
        with self.assertRaisesRegex(ChangelogError, "compare link"):
            roll(text, "0.17.0", "2026-09-20")

    def test_rolling_twice_reproduces_the_shape_it_started_from(self):
        once = roll(FULL, "0.17.0", "2026-09-20")
        once = once.replace("## [Unreleased]\n", "## [Unreleased]\n\n### Added\n\n- Another.\n", 1)
        twice = roll(once, "0.18.0", "2026-09-21")
        self.assertIn(f"[Unreleased]: {BASE}v0.18.0...HEAD", twice)
        self.assertIn(f"[0.18.0]: {BASE}v0.17.0...v0.18.0", twice)
        self.assertLess(twice.index("## [0.18.0]"), twice.index("## [0.17.0]"))


class LiveChangelogTests(unittest.TestCase):
    def test_this_repository_s_changelog_rolls(self):
        text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
        # Unreleased is empty right after a release, which is the refusal, so
        # give it a body first and check the real link block still matches.
        text = text.replace("## [Unreleased]\n", "## [Unreleased]\n\n### Added\n\n- x\n", 1)
        out = roll(text, "9.9.9", "2026-01-01")
        self.assertIn("[9.9.9]: https://github.com/NovusEdge/docket/compare/", out)


if __name__ == "__main__":
    unittest.main()
