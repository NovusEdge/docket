import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.feature_brief as brief


def record(ident, kind, scope, text="t"):
    return {"id": ident, "kind": kind, "scope": scope, "text": text, "state": "adopted"}


class SpecificityTests(unittest.TestCase):
    def test_a_literal_path_outranks_a_blanket_glob(self):
        self.assertGreater(
            brief.specificity("installer/planner.go"), brief.specificity("installer/**")
        )

    def test_the_prefix_stops_at_the_first_wildcard(self):
        self.assertEqual(brief.specificity("installer/**"), len("installer/"))
        self.assertEqual(brief.specificity("docs/*.md"), len("docs/"))
        self.assertEqual(brief.specificity("a/b/c.py"), len("a/b/c.py"))


class AttachTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            record("d1", "decision", ["installer/**"]),
            record("d2", "decision", ["installer/**"]),
            record("d3", "decision", ["installer/planner.go"]),
            record("d4", "decision", ["graph/**"]),
        ]

    def test_an_exact_scope_outranks_a_blanket_one(self):
        got = [e["id"] for e in brief.attach(self.entries, ["installer/planner.go"])]
        self.assertEqual(got[0], "d3")

    def test_a_record_outside_the_files_never_attaches(self):
        got = [e["id"] for e in brief.attach(self.entries, ["installer/planner.go"])]
        self.assertNotIn("d4", got)

    def test_the_blanket_tie_breaks_by_specificity_then_stays_stable(self):
        got = [e["id"] for e in brief.attach(self.entries, ["installer/planner.go"])]
        self.assertEqual(got, ["d3", "d1", "d2"])

    def test_include_attaches_a_record_the_globs_miss(self):
        got = [
            e["id"] for e in brief.attach(self.entries, ["installer/planner.go"], include=["d4"])
        ]
        self.assertIn("d4", got)

    def test_exclude_drops_a_record_the_globs_pulled_in(self):
        got = [
            e["id"] for e in brief.attach(self.entries, ["installer/planner.go"], exclude=["d1"])
        ]
        self.assertNotIn("d1", got)

    def test_exclude_beats_include_for_the_same_id(self):
        got = [
            e["id"]
            for e in brief.attach(
                self.entries, ["installer/planner.go"], include=["d4"], exclude=["d4"]
            )
        ]
        self.assertNotIn("d4", got)

    def test_the_three_numbers_all_come_from_one_scope(self):
        # scope_strength took the max across every scope while specificity took
        # its own max, so a record could print a strength from one glob beside
        # a specificity from another. The printed reason described neither, and
        # a weak scope's high specificity won ties its strong scope had earned.
        # x/a.py matches exactly at 1000 with 6 literal characters. docket/cli
        # matches by prefix at 500 with 10.
        entries = [record("d1", "decision", ["x/a.py", "docket/cli"])]
        [got] = brief.attach(entries, ["x/a.py", "docket/cli/feature.py"])
        self.assertEqual(got["brief_strength"], 1000)
        self.assertEqual(got["brief_specificity"], len("x/a.py"))
        self.assertEqual(got["brief_matches"], 1)

    def test_a_tie_on_strength_still_breaks_on_specificity(self):
        entries = [record("d1", "decision", ["docket/**", "docket/cli/feature.py"])]
        [got] = brief.attach(entries, ["docket/cli/feature.py"])
        self.assertEqual(got["brief_strength"], 1000)
        self.assertEqual(got["brief_specificity"], len("docket/cli/feature.py"))

    def test_a_tie_on_all_three_numbers_breaks_by_file_order(self):
        # d1's id number sorts before c7's, but c7 comes first in the file.
        entries = [
            record("c7", "claim", ["installer/planner.go"]),
            record("d1", "decision", ["installer/planner.go"]),
        ]
        got = [e["id"] for e in brief.attach(entries, ["installer/planner.go"])]
        self.assertEqual(got, ["c7", "d1"])

    def test_reasons_are_reported_on_every_attached_record(self):
        [top, *_] = brief.attach(self.entries, ["installer/planner.go"])
        self.assertEqual(top["brief_strength"], 1000)
        self.assertEqual(top["brief_specificity"], len("installer/planner.go"))
        self.assertEqual(top["brief_matches"], 1)


class ExpandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(
            ["git", "-C", str(self.root), "init", "-b", "main"], check=True, capture_output=True
        )
        for name in ("installer/planner.go", "installer/main.go", "graph/model.go"):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_glob_expands_to_tracked_files(self):
        self.assertEqual(
            brief.expand(self.root, ["installer/**"]),
            ["installer/main.go", "installer/planner.go"],
        )

    def test_an_exact_path_expands_to_itself(self):
        self.assertEqual(brief.expand(self.root, ["graph/model.go"]), ["graph/model.go"])

    def test_a_glob_matching_nothing_expands_to_nothing(self):
        self.assertEqual(brief.expand(self.root, ["nowhere/**"]), [])

    def test_expand_agrees_with_the_matcher_done_uses(self):
        # expand ran its own case-sensitive fnmatch while scope_strength
        # casefolds both sides, so a declared path with an uppercase letter put
        # files in the brief that the intentional set then rejected.
        from docket.feature_outcome import classify

        for declared in ("Installer/**", "installer/**", "INSTALLER/planner.go"):
            tracked = ["installer/main.go", "installer/planner.go", "graph/model.go"]
            self.assertEqual(
                brief.expand(self.root, [declared]),
                classify([declared], tracked)[0],
                declared,
            )


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.feature = {
            "id": "f1",
            "slug": "one",
            "state": "active",
            "text": "do the thing",
            "paths": ["installer/**"],
            "intends": ["the plugin loads"],
            "base": "6f0898e2c1f4a9",
            "branch": "feat/x",
            "log": [],
        }
        self.attached = [
            dict(
                record("d3", "decision", ["installer/planner.go"], "pick a path"),
                brief_strength=1000,
                brief_specificity=20,
                brief_matches=1,
            ),
            dict(
                record("d1", "decision", ["installer/**"], "port to go"),
                brief_strength=700,
                brief_specificity=10,
                brief_matches=4,
            ),
        ]

    def test_the_header_names_the_feature_and_its_state(self):
        out = brief.render(self.feature, self.attached, limit_chars=4000)
        self.assertIn("f1", out)
        self.assertIn("one", out)
        self.assertIn("active", out)

    def test_intends_appear(self):
        out = brief.render(self.feature, self.attached, limit_chars=4000)
        self.assertIn("the plugin loads", out)

    def test_records_appear_strongest_first(self):
        out = brief.render(self.feature, self.attached, limit_chars=4000)
        self.assertLess(out.index("d3"), out.index("d1"))

    def test_each_record_says_why_it_attached(self):
        out = brief.render(self.feature, self.attached, limit_chars=4000)
        self.assertIn("1000", out)
        self.assertIn("700", out)

    def test_the_budget_stops_the_list_and_says_what_it_dropped(self):
        out = brief.render(self.feature, self.attached, limit_chars=260)
        self.assertLessEqual(len(out), 260 + 80)
        self.assertIn("d3", out)
        self.assertIn("1 more", out)


class BlockingTests(unittest.TestCase):
    def test_an_attached_blocked_decision_blocks_the_feature(self):
        attached = [
            {"id": "d1", "kind": "decision", "applicable": False, "blocked_by": ["c9"]},
            {"id": "d2", "kind": "decision", "applicable": True, "blocked_by": []},
        ]
        self.assertEqual(brief.blocking(attached), ["d1"])

    def test_an_open_question_does_not_block(self):
        attached = [{"id": "q1", "kind": "question", "state": "open"}]
        self.assertEqual(brief.blocking(attached), [])

    def test_nothing_blocked_returns_nothing(self):
        attached = [{"id": "d2", "kind": "decision", "applicable": True, "blocked_by": []}]
        self.assertEqual(brief.blocking(attached), [])

    def test_a_superseded_decision_does_not_block(self):
        # ledger.project marks a retired or revoked decision applicable False
        # with blocked_by naming itself. Reading applicable alone made every
        # supersession in scope block the feature: eight false positives and
        # no true ones on this repository's own ledger.
        attached = [{"id": "d1", "kind": "decision", "applicable": False, "blocked_by": ["d1"]}]
        self.assertEqual(brief.blocking(attached), [])

    def test_a_decision_blocked_by_itself_and_a_prerequisite_still_blocks(self):
        attached = [
            {"id": "d1", "kind": "decision", "applicable": False, "blocked_by": ["d1", "c9"]}
        ]
        self.assertEqual(brief.blocking(attached), ["d1"])


class ForcedAttachmentTests(unittest.TestCase):
    def test_an_included_record_the_globs_miss_sorts_first(self):
        entries = [
            record("d1", "decision", ["installer/**"]),
            record("d9", "decision", ["graph/**"]),
        ]
        got = brief.attach(entries, ["installer/planner.go"], include=["d9"])
        # d9 scores 0 because the globs missed it, which is why somebody named
        # it by id. Ranking it by that 0 put it last and the budget dropped it.
        self.assertEqual(got[0]["id"], "d9")


if __name__ == "__main__":
    unittest.main()
