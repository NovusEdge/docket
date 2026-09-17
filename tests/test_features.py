import sys
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


if __name__ == "__main__":
    unittest.main()
