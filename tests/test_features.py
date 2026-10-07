import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.feature_project as feature_project
import docket.features as features
from docket import ledger


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
            features.make_event("start", "slug-one", text="t", paths=["a/**"], status="urgent")

    def test_status_cannot_be_a_terminal_state(self):
        for value in ("done", "abandoned"):
            with self.assertRaisesRegex(features.FeatureError, "status"):
                features.make_event("start", "slug-one", text="t", paths=["a/**"], status=value)

    def test_unknown_event_verb_is_refused(self):
        with self.assertRaisesRegex(features.FeatureError, "event"):
            features.make_event("archive", "slug-one", text="t")

    def test_start_requires_text_and_paths(self):
        with self.assertRaisesRegex(features.FeatureError, "paths"):
            features.make_event("start", "slug-one", text="t")
        with self.assertRaisesRegex(features.FeatureError, "text"):
            features.make_event("start", "slug-one", paths=["a/**"])

    def test_slug_shape_is_enforced(self):
        for bad in ("Has-Caps", "-leading", "has spaces", ""):
            with self.assertRaisesRegex(features.FeatureError, "slug"):
                features.make_event("note", bad, text="t")

    def test_malformed_id_is_refused(self):
        event = features.make_event("note", "slug-one", text="t")
        event["id"] = "d3"
        with self.assertRaisesRegex(features.FeatureError, "id"):
            features.validate_event(event)

    def test_a_field_the_schema_gained_later_is_filled_on_read(self):
        # Every line already written lacks it, and every field is required.
        event = features.make_event("note", "slug-one", text="t")
        del event["cleared"]
        self.assertEqual(features.validate_event(event)["cleared"], [])

    def test_a_schema_one_event_is_refused_with_the_migrate_instruction(self):
        event = dict(features.make_event("note", "slug-one", text="t"), schema=1)
        with self.assertRaisesRegex(features.FeatureSchemaTooOld, "docket migrate"):
            features.validate_event(event)
        self.assertTrue(issubclass(features.FeatureSchemaTooOld, features.FeatureError))

    def test_a_line_that_declares_no_schema_is_still_refused(self):
        event = features.make_event("note", "slug-one", text="t")
        del event["schema"]
        with self.assertRaisesRegex(features.FeatureError, "schema"):
            features.validate_event(event)

    def test_cleared_names_only_a_clearable_field(self):
        with self.assertRaisesRegex(features.FeatureError, "cannot clear"):
            features.make_event("amend", "slug-one", cleared=["paths"])

    def test_cleared_belongs_to_amend(self):
        with self.assertRaisesRegex(features.FeatureError, "cleared belongs to amend"):
            features.make_event("note", "slug-one", text="t", cleared=["include"])


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
        self.assertEqual(self.add("start", "one", text="t", paths=["a/**"])["id"], "f1")
        self.assertEqual(self.add("note", "one", text="n")["id"], "f2")
        self.assertEqual(self.add("done", "one")["id"], "f3")

    def test_appended_events_read_back_in_order(self):
        self.add("start", "one", text="t", paths=["a/**"])
        self.add("note", "one", text="n")
        self.assertEqual([e["event"] for e in features.read(self.path)], ["start", "note"])

    def test_a_corrupt_line_names_its_line_number(self):
        self.path.write_text('{"schema":2,"event":"nope"}\n', encoding="utf-8")
        with self.assertRaisesRegex(features.FeatureError, "line 1"):
            features.read(self.path)

    def schema_one_line(self, ident="f1"):
        event = dict(
            features.make_event("start", "one", text="t", paths=["a/**"]), id=ident, schema=1
        )
        return json.dumps(event) + "\n"

    def test_read_refuses_a_schema_one_store_naming_the_line(self):
        self.path.write_text(self.schema_one_line(), encoding="utf-8")
        with self.assertRaisesRegex(features.FeatureSchemaTooOld, "line 1.*docket migrate"):
            features.read(self.path)

    def test_an_archive_at_schema_one_still_sets_the_id_floor(self):
        from docket.feature_archive import highest_archived_id

        archive = self.path.parent / "archive"
        archive.mkdir()
        (archive / "features-abc.jsonl").write_text(self.schema_one_line("f7"), encoding="utf-8")
        self.assertEqual(highest_archived_id(self.path), 7)
        self.path.write_text("", encoding="utf-8")
        started = features.make_event("start", "one", text="t", paths=["a/**"])
        self.assertEqual(features.append(self.path, started)["id"], "f8")

    def test_qualified_id_appends_eight_characters_of_base(self):
        event = self.add("start", "one", text="t", paths=["a/**"], base="6f0898e2c1f4a9")
        self.assertEqual(features.qualified(event), "f1@6f0898e2")

    def test_qualified_id_is_the_bare_id_without_a_base(self):
        event = self.add("start", "one", text="t", paths=["a/**"])
        self.assertEqual(features.qualified(event), "f1")


class PathTests(unittest.TestCase):
    def test_features_file_sits_beside_the_ledger(self):
        import docket.env as env

        self.assertEqual(env.features_path().parent, env.ledger_path().parent)
        self.assertEqual(env.features_path().name, "features.jsonl")


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "features.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, event, slug, **fields):
        return features.append(self.path, features.make_event(event, slug, **fields))

    def current(self):
        return feature_project.project(features.read(self.path))

    def test_a_start_projects_as_active(self):
        self.add("start", "one", text="t", paths=["a/**"])
        [feature] = self.current()
        self.assertEqual(feature["state"], "active")
        self.assertEqual(feature["id"], "f1")

    def test_amend_replaces_a_field_wholesale(self):
        self.add("start", "one", text="t", paths=["a/**", "b/**"])
        self.add("amend", "one", paths=["c/**"])
        self.assertEqual(self.current()[0]["paths"], ["c/**"])

    def test_amend_changes_the_declared_status(self):
        self.add("start", "one", text="t", paths=["a/**"])
        self.add("amend", "one", status="paused")
        self.assertEqual(self.current()[0]["state"], "paused")

    def test_a_terminal_event_outranks_the_declared_status(self):
        self.add("start", "one", text="t", paths=["a/**"])
        self.add("amend", "one", status="paused")
        self.add("done", "one")
        self.assertEqual(self.current()[0]["state"], "done")

    def test_notes_accumulate_in_the_log(self):
        self.add("start", "one", text="t", paths=["a/**"])
        self.add("note", "one", text="first")
        self.add("note", "one", text="second")
        self.assertEqual([n["text"] for n in self.current()[0]["log"]], ["first", "second"])

    def test_a_second_start_on_an_open_slug_is_refused(self):
        self.add("start", "one", text="t", paths=["a/**"])
        with self.assertRaisesRegex(features.FeatureError, "already open"):
            self.add("start", "one", text="t", paths=["b/**"])

    def test_a_slug_may_be_reused_after_a_close(self):
        self.add("start", "one", text="first", paths=["a/**"])
        self.add("done", "one")
        self.add("start", "one", text="second", paths=["b/**"])
        states = sorted(f["state"] for f in self.current())
        self.assertEqual(states, ["active", "done"])

    def test_amend_on_a_closed_feature_is_refused(self):
        self.add("start", "one", text="t", paths=["a/**"])
        self.add("done", "one")
        with self.assertRaisesRegex(features.FeatureError, "closed"):
            self.add("amend", "one", status="paused")

    def test_resolve_prefers_the_open_feature(self):
        self.add("start", "one", text="first", paths=["a/**"])
        self.add("done", "one")
        self.add("start", "one", text="second", paths=["b/**"])
        self.assertEqual(feature_project.resolve(self.current(), "one")["text"], "second")

    def test_two_events_sharing_an_id_are_refused(self):
        self.add("start", "alpha", text="t", paths=["a/**"])
        line = self.path.read_text(encoding="utf-8").splitlines()[0]
        self.path.write_text(
            self.path.read_text(encoding="utf-8") + line.replace('"alpha"', '"beta"') + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(features.FeatureError, "already used by alpha"):
            self.current()

    def test_resolve_by_id_reaches_a_closed_feature(self):
        self.add("start", "one", text="first", paths=["a/**"])
        self.add("done", "one")
        self.assertEqual(feature_project.resolve(self.current(), "f1")["state"], "done")

    def test_resolve_names_closed_ids_when_only_those_match(self):
        self.add("start", "one", text="first", paths=["a/**"])
        self.add("done", "one")
        with self.assertRaisesRegex(features.FeatureError, "f1"):
            feature_project.resolve(self.current(), "one")


TS = "2026-01-01T00:00:00+00:00"


def stored_key(kind, text):
    """The key recipe as it stood before id masking, for events written then."""
    raw = "\0".join((kind, TS, "t", "s", text))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def claim(ident, text):
    return ledger.make_record(
        "claim", text, state="accepted", author="t", session="s", ts=TS, record_id=ident
    )


class RecordKeyTests(unittest.TestCase):
    def test_a_headline_with_no_id_token_keeps_its_key(self):
        self.assertEqual(
            ledger.record_key(claim("c1", "No ids in this headline")),
            stored_key("claim", "No ids in this headline"),
        )

    def test_a_headline_id_token_does_not_move_the_key(self):
        before = claim("c3", "Contradicts d2 outright")
        after = claim("c2", "Contradicts d1 outright")
        self.assertEqual(ledger.record_key(before), ledger.record_key(after))
        self.assertNotEqual(ledger.record_key(before), stored_key("claim", before["text"]))

    def test_a_key_stored_before_the_change_still_rebinds(self):
        entries = [claim("c1", "Alpha"), claim("c2", "Beta")]
        keys = {"c9": stored_key("claim", "Beta")}
        self.assertEqual(ledger.rebind(["c9"], keys, entries), ["c2"])

    def test_stale_keys_names_an_id_whose_key_matches_no_record(self):
        entries = [claim("c1", "Alpha"), claim("c2", "Beta")]
        keys = {"c1": stored_key("claim", "Alpha"), "c2": "0" * 12, "c3": "1" * 12}
        self.assertEqual(ledger.stale_keys(["c1", "c2", "c3", "c4"], keys, entries), ["c2"])

    def test_an_id_whose_key_names_another_record_is_rebound_not_stale(self):
        entries = [claim("c1", "Alpha"), claim("c2", "Beta")]
        keys = {"c1": stored_key("claim", "Beta")}
        self.assertEqual(ledger.stale_keys(["c1"], keys, entries), [])


class RemapEventsTests(unittest.TestCase):
    def setUp(self):
        self.by_id = {
            "c3": claim("c3", "Third premise"),
            "d1": ledger.make_record(
                "decision",
                "Cache layer sits behind reads",
                state="adopted",
                choice="Cache",
                alternatives=["No cache"],
                rationale="Reads dominate",
                author="t",
                session="s",
                ts=TS,
                record_id="d1",
            ),
            "q1": ledger.make_record(
                "question", "Which store?", author="t", session="s", ts=TS, record_id="q1"
            ),
        }
        self.mapping = {"c4": "c3", "d2": "d1", "q5": "q1"}

    def event(self, **fields):
        return dict(
            features.make_event("start", "one", text="t", paths=["a/**"], ts=TS, **fields),
            id="f1",
            schema=1,
        )

    def test_every_ledger_ref_field_is_rewritten_and_keys_recomputed(self):
        old = self.event(
            include=["c4"],
            exclude=["d2"],
            held=["q5"],
            failed=["c4", "d9"],
            unanswered=["q5"],
            keys={"c4": "a" * 12, "d2": "b" * 12, "q5": "c" * 12},
        )
        [new] = features.remap_events([old], self.mapping, self.by_id)
        self.assertEqual(new["schema"], 2)
        self.assertEqual(new["include"], ["c3"])
        self.assertEqual(new["exclude"], ["d1"])
        self.assertEqual(new["held"], ["q1"])
        self.assertEqual(new["failed"], ["c3", "d9"])
        self.assertEqual(new["unanswered"], ["q1"])
        self.assertEqual(
            new["keys"], {i: ledger.record_key(self.by_id[i]) for i in ("c3", "d1", "q1")}
        )

    def test_a_key_whose_record_is_missing_is_kept_under_the_new_id(self):
        old = self.event(include=["c4"], keys={"c4": "a" * 12})
        [new] = features.remap_events([old], self.mapping, {})
        self.assertEqual(new["keys"], {"c3": "a" * 12})

    def test_a_schema_two_event_passes_through_untouched(self):
        done = dict(self.event(include=["c3"]), schema=2)
        self.assertEqual(features.remap_events([done], {"c3": "c2"}, self.by_id), [done])


if __name__ == "__main__":
    unittest.main()
