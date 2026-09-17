import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.features as features


class EventSchemaTests(unittest.TestCase):
    def test_make_event_fills_defaults_and_keeps_given_fields(self):
        event = features.make_event(
            "start", "opencode-discovery", text="place the plugin", paths=["installer/*.go"]
        )
        self.assertEqual(event["event"], "start")
        self.assertEqual(event["slug"], "opencode-discovery")
        self.assertEqual(event["status"], "active")
        self.assertEqual(event["schema"], features.SCHEMA)
        self.assertEqual(event["include"], [])
        self.assertEqual(event["exclude"], [])

    def test_unknown_field_is_refused(self):
        event = features.make_event("note", "slug-one", text="a note")
        event["priority"] = "high"
        with self.assertRaisesRegex(features.FeatureError, "unknown field"):
            features.validate_event(event)

    def test_status_outside_the_enum_is_refused(self):
        with self.assertRaisesRegex(features.FeatureError, "status"):
            features.make_event("start", "slug-one", text="t", paths=["a"], status="urgent")

    def test_status_cannot_be_a_terminal_state(self):
        for value in ("done", "abandoned"):
            with self.assertRaisesRegex(features.FeatureError, "status"):
                features.make_event("start", "slug-one", text="t", paths=["a"], status=value)

    def test_unknown_event_verb_is_refused(self):
        with self.assertRaisesRegex(features.FeatureError, "event"):
            features.make_event("archive", "slug-one", text="t")

    def test_start_requires_text_and_paths(self):
        with self.assertRaisesRegex(features.FeatureError, "paths"):
            features.make_event("start", "slug-one", text="t")
        with self.assertRaisesRegex(features.FeatureError, "text"):
            features.make_event("start", "slug-one", paths=["a"])

    def test_slug_shape_is_enforced(self):
        for bad in ("Has-Caps", "-leading", "has spaces", ""):
            with self.assertRaisesRegex(features.FeatureError, "slug"):
                features.make_event("note", bad, text="t")

    def test_malformed_id_is_refused(self):
        event = features.make_event("note", "slug-one", text="t")
        event["id"] = "d3"
        with self.assertRaisesRegex(features.FeatureError, "id"):
            features.validate_event(event)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "features.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, event, slug, **fields):
        return features.append(self.path, features.make_event(event, slug, **fields))

    def test_reading_a_missing_file_returns_no_events(self):
        self.assertEqual(features.read(self.path), [])

    def test_ids_are_allocated_in_sequence(self):
        self.assertEqual(self.add("start", "one", text="t", paths=["a"])["id"], "f1")
        self.assertEqual(self.add("note", "one", text="n")["id"], "f2")
        self.assertEqual(self.add("done", "one")["id"], "f3")

    def test_appended_events_read_back_in_order(self):
        self.add("start", "one", text="t", paths=["a"])
        self.add("note", "one", text="n")
        self.assertEqual([e["event"] for e in features.read(self.path)], ["start", "note"])

    def test_a_corrupt_line_names_its_line_number(self):
        self.path.write_text('{"schema":1,"event":"nope"}\n', encoding="utf-8")
        with self.assertRaisesRegex(features.FeatureError, "line 1"):
            features.read(self.path)

    def test_qualified_id_appends_eight_characters_of_base(self):
        event = self.add("start", "one", text="t", paths=["a"], base="6f0898e2c1f4a9")
        self.assertEqual(features.qualified(event), "f1@6f0898e2")

    def test_qualified_id_is_the_bare_id_without_a_base(self):
        event = self.add("start", "one", text="t", paths=["a"])
        self.assertEqual(features.qualified(event), "f1")


class PathTests(unittest.TestCase):
    def test_features_file_sits_beside_the_ledger(self):
        import docket.env as env

        self.assertEqual(env.features_path().parent, env.ledger_path().parent)
        self.assertEqual(env.features_path().name, "features.jsonl")


if __name__ == "__main__":
    unittest.main()
