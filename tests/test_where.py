import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from docket import ledger, where

# graph/testdata/tokenizer_cases.json holds this table. The viewer previews
# text terms with its own tokenizer, so both must split every case the same
# way; graph/main_test.go TestFilterTokenizerMatchesPython reads the same file.
_CASES_PATH = Path(__file__).parent.parent / "graph" / "testdata" / "tokenizer_cases.json"
with _CASES_PATH.open(encoding="utf-8") as _f:
    SHARED_CASES = [
        (case["input"], [(t["field"], t["value"], t["negated"]) for t in case["terms"]])
        for case in json.load(_f)
    ]


def entry(**fields):
    record = {
        "id": "c1",
        "kind": "claim",
        "text": "",
        "state": "accepted",
        "recorded_state": "accepted",
        "ts": "2026-09-10T12:00:00+00:00",
        "author": "alice",
        "branch": "main",
        "scope": [],
        "rationale": "",
        "pinned": False,
        "retired_by": "",
    }
    record.update(fields)
    return record


def hit(query, **fields):
    return where.parse(query).matches(entry(**fields))


class TokenizerTests(unittest.TestCase):
    def test_cases_shared_with_the_viewer(self):
        for query, expected in SHARED_CASES:
            terms = [(t.field, t.value, t.negated) for t in where.parse(query).terms]
            self.assertEqual(terms, expected, query)


class TextTermTests(unittest.TestCase):
    def test_text_searches_id_text_choice_and_rationale(self):
        self.assertTrue(hit("c1"))
        self.assertTrue(hit("cache", text="The cache lives in Redis."))
        self.assertTrue(hit("redis", kind="decision", choice="Redis"))
        self.assertTrue(hit("latency", rationale="Latency matters."))
        self.assertFalse(hit("alice"))
        self.assertFalse(hit("claim"))

    def test_words_and_each_other(self):
        self.assertTrue(hit("cache redis", text="cache in redis"))
        self.assertFalse(hit("cache postgres", text="cache in redis"))

    def test_a_negated_word_excludes(self):
        self.assertFalse(hit("-redis", text="cache in redis"))
        self.assertTrue(hit("-postgres", text="cache in redis"))

    def test_a_quoted_phrase_keeps_its_space(self):
        self.assertTrue(hit('"in redis"', text="cache in redis"))
        self.assertFalse(hit('"redis in"', text="cache in redis"))

    def test_a_colon_inside_a_quoted_term_stays_text(self):
        query = where.parse('"d12:"')
        self.assertFalse(query.has_fields)
        self.assertTrue(query.matches(entry(text="see d12: the cache")))
        self.assertFalse(query.matches(entry(text="see d12 the cache")))

    def test_case_is_ignored(self):
        self.assertTrue(hit("REDIS", text="redis"))
        self.assertTrue(hit("KIND:Decision", kind="decision"))

    def test_an_empty_query_matches_everything(self):
        self.assertTrue(hit(""))
        self.assertTrue(hit("   "))


class FieldTermTests(unittest.TestCase):
    def test_kind(self):
        self.assertTrue(hit("kind:claim"))
        self.assertFalse(hit("kind:decision"))

    def test_repeats_of_one_field_or_each_other(self):
        query = where.parse("kind:claim kind:decision")
        self.assertTrue(query.matches(entry(kind="claim")))
        self.assertTrue(query.matches(entry(kind="decision")))
        self.assertFalse(query.matches(entry(kind="question")))

    def test_different_fields_and_each_other(self):
        self.assertTrue(hit("kind:decision author:bob", kind="decision", author="bob"))
        self.assertFalse(hit("kind:decision author:bob", kind="decision", author="alice"))

    def test_state_is_the_effective_state(self):
        answered = {"kind": "question", "state": "resolved", "recorded_state": "open"}
        self.assertTrue(hit("state:resolved", **answered))
        self.assertFalse(hit("state:open", **answered))

    def test_is_values(self):
        self.assertTrue(hit("is:pinned", pinned=True))
        self.assertFalse(hit("is:pinned"))
        self.assertTrue(hit("is:corrected", corrections=["c1.1"]))
        self.assertFalse(hit("is:corrected"))
        self.assertTrue(hit("is:retired", retired_by="c2"))
        self.assertFalse(hit("is:retired"))

    def test_is_terms_and_each_other(self):
        self.assertFalse(hit("is:pinned is:corrected", pinned=True))
        self.assertTrue(hit("is:pinned is:corrected", pinned=True, corrections=["c1.1"]))

    def test_author_and_branch_match_a_substring(self):
        self.assertTrue(hit('author:"a teammate"', author="A Teammate (bot)"))
        self.assertFalse(hit('author:"a teammate"', author="teammate"))
        self.assertTrue(hit("branch:feat", branch="feature/x"))
        self.assertFalse(hit("branch:feat", branch="main"))

    def test_a_negated_field_term_ands_alone(self):
        self.assertFalse(hit("-kind:question", kind="question"))
        self.assertTrue(hit("-kind:question", kind="claim"))
        self.assertFalse(hit("kind:claim kind:decision -is:pinned", pinned=True))
        self.assertTrue(hit("kind:claim kind:decision -is:pinned"))


class DateTermTests(unittest.TestCase):
    def test_after_includes_the_day_and_before_excludes_it(self):
        self.assertTrue(hit("after:2026-09-10"))
        self.assertFalse(hit("after:2026-09-11"))
        self.assertTrue(hit("before:2026-09-11"))
        self.assertFalse(hit("before:2026-09-10"))

    def test_the_date_is_taken_in_utc(self):
        # 23:30 at UTC-2 is 01:30 on the next day in UTC.
        self.assertTrue(hit("after:2026-09-02", ts="2026-09-01T23:30:00-02:00"))
        self.assertFalse(hit("before:2026-09-02", ts="2026-09-01T23:30:00-02:00"))

    def test_an_empty_or_unparsable_ts_never_matches(self):
        for ts in ("", "yesterday"):
            self.assertFalse(hit("after:2000-01-01", ts=ts), ts)
            self.assertFalse(hit("before:2999-01-01", ts=ts), ts)

    def test_negation_inverts_the_date_term(self):
        self.assertTrue(hit("-after:2000-01-01", ts="yesterday"))


class ScopeTermTests(unittest.TestCase):
    def test_a_path_matches_exact_glob_and_directory_scopes(self):
        for scope in (["docket/ledger.py"], ["docket/*.py"], ["docket/"]):
            self.assertTrue(hit("scope:docket/ledger.py", scope=scope), scope)
        self.assertFalse(hit("scope:docket/ledger.py", scope=["graph/main.go"]))

    def test_a_top_level_file_matches_an_equal_entry(self):
        self.assertTrue(hit("scope:README.md", scope=["README.md"]))
        self.assertFalse(hit("scope:README.md", scope=["docs/README.md"]))

    def test_a_directory_matches_entries_under_it_and_entries_that_govern_it(self):
        for scope in (["graph/main.go"], ["graph/**"], ["graph"], ["graph/"]):
            self.assertTrue(hit("scope:graph/", scope=scope), scope)
        self.assertTrue(hit("scope:docket/cli/", scope=["docket/"]))
        self.assertFalse(hit("scope:graph/", scope=["docs/graph.md"]))

    def test_scope_paths_ignore_case(self):
        self.assertTrue(hit("scope:Graph/Main.go", scope=["graph/main.go"]))


class BlockedTests(unittest.TestCase):
    def test_blocked_ignores_retired_and_revoked_decisions(self):
        def decision(ident, text, **kwargs):
            return ledger.make_record(
                "decision", text, choice=f"option {ident}", author="t", record_id=ident, **kwargs
            )

        entries = ledger.project(
            [
                ledger.make_record("claim", "Unassessed premise.", author="t", record_id="c1"),
                decision("d2", "Blocked choice.", depends_on=["c1"]),
                decision("d3", "Revoked choice.", state="revoked"),
                decision("d4", "Old choice."),
                decision("d5", "New choice.", supersedes=["d4"]),
            ]
        )
        by_id = {item["id"]: item for item in entries}
        # The fixture holds the trap: both carry their own id in blocked_by.
        self.assertEqual(by_id["d3"]["blocked_by"], ["d3"])
        self.assertEqual(by_id["d4"]["blocked_by"], ["d4"])
        query = where.parse("is:blocked")
        self.assertEqual([item["id"] for item in entries if query.matches(item)], ["d2"])


class ErrorTests(unittest.TestCase):
    def assertRefused(self, query, *fragments):
        with self.assertRaises(where.WhereError) as caught:
            where.parse(query)
        for fragment in fragments:
            self.assertIn(fragment, str(caught.exception))

    def test_where_error_is_a_value_error(self):
        self.assertTrue(issubclass(where.WhereError, ValueError))

    def test_an_unknown_field_names_the_term_and_lists_the_fields(self):
        self.assertRefused(
            "colour:red",
            "colour:red",
            "after, author, before, branch, is, kind, scope, state",
            "quote",
        )

    def test_an_unknown_kind(self):
        self.assertRefused("kind:note", "kind:note", "claim, decision, question")

    def test_an_unknown_state(self):
        self.assertRefused("state:done", "state:done", "adopted", "unassessed")

    def test_retired_and_blocked_are_not_states(self):
        self.assertRefused("state:retired", "use is:retired")
        self.assertRefused("state:blocked", "use is:blocked")

    def test_an_unknown_is_value(self):
        self.assertRefused("is:open", "is:open", "blocked, corrected, pinned, retired")

    def test_a_malformed_date(self):
        for query in ("after:2026-9-1", "before:2026-13-01", "after:20260901", "after:yesterday"):
            self.assertRefused(query, query, "YYYY-MM-DD")

    def test_a_field_with_no_value(self):
        self.assertRefused("kind:", "kind:", "needs a value")

    def test_a_negated_term_keeps_its_sign_in_the_message(self):
        self.assertRefused("-kind:note", "-kind:note")


class FlagTests(unittest.TestCase):
    def test_wants_retired(self):
        self.assertTrue(where.parse("is:retired").wants_retired)
        self.assertTrue(where.parse("kind:decision is:retired").wants_retired)
        self.assertFalse(where.parse("-is:retired").wants_retired)
        self.assertFalse(where.parse("retired").wants_retired)
        self.assertFalse(where.parse("").wants_retired)

    def test_has_fields(self):
        self.assertTrue(where.parse("kind:claim").has_fields)
        self.assertTrue(where.parse("-author:bob").has_fields)
        self.assertFalse(where.parse("cache -redis").has_fields)
        self.assertFalse(where.parse('"kind:claim"').has_fields)


if __name__ == "__main__":
    unittest.main()
