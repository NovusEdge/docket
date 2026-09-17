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


if __name__ == "__main__":
    unittest.main()
