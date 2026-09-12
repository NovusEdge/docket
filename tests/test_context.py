import unittest
import re

from lib.docket_context import build_context, _term_weights
from lib.docket_ledger import make_record, project


def entry(
    ident,
    kind,
    text,
    *,
    state=None,
    scope=(),
    supports=(),
    depends_on=(),
    answers=(),
    pinned=False,
    choice="",
    alternatives=(),
    rationale="",
    evidence=(),
    revisit="",
    cost_if_wrong="",
    decided_by="",
    supersedes=(),
):
    kwargs = dict(
        state=state,
        scope=list(scope),
        rationale=rationale,
        supports=[list(group) for group in supports],
        answers=list(answers),
        supersedes=list(supersedes),
        evidence=list(evidence),
        revisit=revisit,
        cost_if_wrong=cost_if_wrong,
        pinned=pinned,
        author="tester",
        session="test-session",
        branch="main",
        ts=f"2026-09-12T00:00:{int(ident[1:]):02d}Z",
        record_id=ident,
    )
    if kind == "decision":
        kwargs.update(
            choice=choice or "chosen",
            alternatives=list(alternatives),
            depends_on=list(depends_on),
            decided_by=decided_by,
        )
    return make_record(kind, text, **kwargs)


def projected(records):
    return project(records)


class ContextTests(unittest.TestCase):
    def test_empty_entries_cost_no_context(self):
        self.assertEqual(build_context([], ledger="project"), "")

    def test_revision_is_deterministic_and_changes_with_history(self):
        records = [entry("c1", "claim", "Use the stable API")]
        first = build_context(projected(records), ledger="project")
        second = build_context(projected(records), ledger="project")
        self.assertEqual(first, second)
        changed = build_context(projected(records + [entry("q2", "question", "Why?")]), ledger="project")
        self.assertNotEqual(first, changed)
        self.assertIn("revision", first)
        self.assertIn("project", first)

    def test_pinned_and_task_matches_rank_before_unrelated_records(self):
        records = [
            entry("c1", "claim", "Unrelated deployment detail", scope=("docs/deploy",)),
            entry("d2", "decision", "Choose SQLite for tests", choice="SQLite", pinned=True),
            entry("d3", "decision", "Choose Postgres for production", choice="Postgres", scope=("app/db",)),
            entry("c4", "claim", "The database backup is encrypted", scope=("ops/backup",)),
        ]
        rendered = build_context(projected(records), query="database", files=("app/db/models.py",), ledger="repo")
        self.assertLess(rendered.index("### d3 "), rendered.index("### d2 "))
        self.assertLess(rendered.index("### d3 "), rendered.index("### c4 "))
        self.assertNotIn("### c1 ", rendered)
        self.assertIn("c1 claim", rendered)
        self.assertIn("Choose Postgres for production", rendered)

    def test_related_records_keep_complete_formulas_and_warn_on_premises(self):
        records = [
            entry("c1", "claim", "The cache is reliable", state="disputed"),
            entry("c2", "claim", "The service has a health check", state="accepted"),
            entry(
                "d3",
                "decision",
                "Use the cache",
                state="adopted",
                supports=(("c1", "c2"), ("c2",)),
                depends_on=("c1",),
                evidence=({"ref": "issue-7", "checked_at": "2026-09-11"},),
                choice="cache",
                decided_by="self-report",
            ),
        ]
        rendered = build_context(projected(records), query="cache", ledger="repo")
        self.assertIn('["c1", "c2"]', rendered)
        self.assertIn("c1", rendered)
        self.assertIn("disputed", rendered.lower())
        self.assertIn("full text:", rendered.lower())
        self.assertIn("issue-7", rendered)
        self.assertIn("not freshly verified", rendered.lower())
        self.assertIn("applicable: false", rendered)
        self.assertIn('blocked_by: ["c1"]', rendered)
        self.assertIn("decided by: self-report", rendered)

    def test_retired_record_only_appears_as_cited_historical_premise(self):
        records = [
            entry("c1", "claim", "Old premise", state="accepted"),
            entry("c2", "claim", "Current premise"),
            entry("c3", "claim", "Retire old", state="accepted", supersedes=("c1",)),
            entry("d4", "decision", "Keep current premise", supports=(("c1",),)),
        ]
        plain = build_context(projected(records), query="unrelated", ledger="repo")
        self.assertNotIn("Old premise", plain)
        cited = build_context(projected(records), query="Keep current", ledger="repo")
        self.assertIn("Old premise", cited)
        self.assertIn("retired", cited.lower())

    def test_budget_is_hard_unicode_safe_and_never_splits_a_block(self):
        records = [
            entry("c1", "claim", "Unicode premise: café 東京 漢", state="accepted", pinned=True),
            entry("c2", "claim", "A second long premise that should be omitted", state="accepted", pinned=True),
        ]
        rendered = build_context(projected(records), ledger="repo", max_chars=700)
        self.assertLessEqual(len(rendered), 700)
        self.assertIn("café 東京 漢", rendered)
        # A record is either present with its complete proposition or absent.
        self.assertNotIn("### c2 ", rendered)
        self.assertIn("c2 claim accepted", rendered)
        self.assertIn("index:", rendered)

    def test_all_records_and_task_briefing_have_fixed_fixture_coverage(self):
        records = [
            entry("d1", "decision", "Adopt API versioning", choice="v2", pinned=True),
            entry("c2", "claim", "Billing uses integer cents", scope=("billing",)),
            entry("d3", "decision", "Use Postgres", choice="postgres", scope=("storage",)),
            entry("c4", "claim", "The email copy is approved", scope=("marketing",)),
            entry("q5", "question", "Who owns the on call rotation?", scope=("ops",)),
        ]
        full = build_context(projected(records), ledger="repo", all_records=True)
        task = build_context(projected(records), query="storage", ledger="repo")
        self.assertLess(len(task), len(full))
        self.assertIn("Use Postgres", task)
        self.assertNotIn("### c4 ", task)
        self.assertIn("c4 claim", task)
        self.assertIn("Adopt API versioning", task)
        ids = lambda output: set(re.findall(r"^### ([cdq]\d+) ", output, re.M))
        self.assertEqual(ids(full), {"d1", "c2", "d3", "c4", "q5"})
        self.assertEqual(ids(task), {"d1", "d3"})

    def test_omitted_root_does_not_leave_orphan_neighbors(self):
        records = [entry("c1", "claim", "Small premise", state="accepted"),
                   entry("d2", "decision", "Unique task", rationale="x" * 5000,
                         supports=(("c1",),))]
        output = build_context(projected(records), query="Unique", max_chars=900)
        self.assertNotIn("### c1", output)
        self.assertNotIn("### d2", output)
        self.assertIn("d2 decision", output)
        self.assertIn("docket show", output)
        self.assertLessEqual(len(output), 900)

    def test_resolved_question_and_reverse_prerequisite_retrieve_related_records(self):
        records = [entry("q1", "question", "Which backend?"),
                   entry("c2", "claim", "Unique prerequisite", state="accepted"),
                   entry("d3", "decision", "Adopt storage", answers=("q1",),
                         depends_on=("c2",))]
        output = build_context(projected(records), query="Which backend")
        self.assertIn("### q1 | question | resolved", output)
        self.assertIn("role: inquiry", output)
        self.assertIn("### d3 | decision | adopted [related record]", output)
        self.assertNotIn("related premise", output)
        reverse = build_context(projected(records), query="Unique prerequisite")
        self.assertIn("### d3 | decision", reverse)

    def test_stronger_relevance_beats_pin_and_paths_are_normalized(self):
        records = [entry("c1", "claim", "Topic", pinned=True),
                   entry("c2", "claim", "Topic", scope=("src/*.py",)),
                   entry("c3", "claim", "Directory rule", scope=("src/sub",)),
                   entry("c4", "claim", "Component rule", scope=("billing",))]
        history = projected(records)
        output = build_context(history, query="Topic", files=(".\\src\\module.py",))
        self.assertLess(output.index("### c2"), output.index("### c1"))
        directory = build_context(history, files=("./src/sub/file.go",))
        self.assertIn("### c3", directory)
        component = build_context(history, files=("billing",))
        self.assertNotIn("### c4", component)
        self.assertIn("### c4", build_context(history, query="billing"))

    def test_direct_api_budgets_and_large_metadata(self):
        history = projected([entry("c1", "claim", "Full Unicode café 東京", rationale="X" * 10000)])
        for invalid in (511, 0, -1, "900", None, True, 900.5):
            with self.assertRaises(ValueError):
                build_context(history, max_chars=invalid)
        for budget in (512, 700, 900, 1500):
            output = build_context(history, ledger="z" * 5000, query="Full " * 1000,
                                   all_records=True, max_chars=budget)
            self.assertLessEqual(len(output), budget)
            self.assertNotIn("### c1", output)
            self.assertIn("c1", output)
            self.assertTrue(output.endswith("\n"))

    def test_record_blocks_compact_repeated_decision_metadata_without_loss(self):
        records = [
            entry(
                "d1",
                "decision",
                "Select the stable API",
                state="adopted",
                choice="v2",
                alternatives=("v2", "v1"),
                rationale="v2",
            )
        ]
        rendered = build_context(projected(records), ledger="repo")
        self.assertIn('alternatives: ["v1"]', rendered)
        self.assertNotIn('alternatives: ["v2", "v1"]', rendered)
        self.assertNotIn("rationale: v2", rendered)
        self.assertNotIn("effective state:", rendered)
        self.assertTrue(rendered.endswith("\n"))


    def test_every_current_record_appears_in_one_tier(self):
        records = [
            entry("d1", "decision", "Adopt API versioning", choice="v2"),
            entry("c2", "claim", "Billing uses integer cents", scope=("billing",)),
            entry("d3", "decision", "Use Postgres", choice="postgres", scope=("storage",)),
            entry("c4", "claim", "The email copy is approved", scope=("marketing",)),
        ]
        rendered = build_context(projected(records), query="storage", ledger="repo")
        full = set(re.findall(r"^### ([cdq]\d+) ", rendered, re.M))
        index = set(re.findall(r"^([cdq]\d+) (?:claim|decision|question) ", rendered, re.M))
        self.assertIn("d3", full)
        self.assertEqual(full | index, {"d1", "c2", "d3", "c4"})
        self.assertEqual(full & index, set())

    def test_index_line_states_kind_and_state_and_clips_text(self):
        long_text = "A premise whose text runs well past the sixty character clip point"
        records = [
            entry("d1", "decision", "Use Postgres", choice="postgres", scope=("storage",)),
            entry("c2", "claim", long_text, state="accepted"),
        ]
        rendered = build_context(projected(records), query="storage", ledger="repo")
        line = next(l for l in rendered.splitlines() if l.startswith("c2 "))
        self.assertTrue(line.startswith("c2 claim accepted  "))
        self.assertLessEqual(len(line), 90)
        self.assertIn("A premise whose text runs well past", line)
        self.assertNotIn("clip point", line)

    def test_precise_scope_outranks_a_glob_match(self):
        records = [
            entry("d1", "decision", "Old storage decision", choice="x", scope=("storage/**",)),
            entry("d2", "decision", "Recent storage decision", choice="y", scope=("storage/db.py",)),
        ]
        rendered = build_context(projected(records), files=("storage/db.py",), ledger="repo")
        self.assertLess(rendered.index("### d2 "), rendered.index("### d1 "))

    def test_recency_orders_records_of_equal_scope_strength(self):
        records = [
            entry("d1", "decision", "Older renderer decision", choice="x", scope=("lib/**",)),
            entry("d2", "decision", "Newer renderer decision", choice="y", scope=("lib/**",)),
        ]
        rendered = build_context(projected(records), files=("lib/docket_context.py",), ledger="repo")
        self.assertLess(rendered.index("### d2 "), rendered.index("### d1 "))

    def test_selection_reason_names_the_score_and_components(self):
        records = [entry("d1", "decision", "Renderer budget", choice="y", scope=("lib/**",))]
        rendered = build_context(projected(records), files=("lib/docket_context.py",), ledger="repo")
        self.assertRegex(rendered, r"selection: score \d+ \| ")
        self.assertIn("scope=", rendered)

    def test_rare_term_outranks_a_term_present_in_most_records(self):
        records = [
            entry("d1", "decision", "decision about caching", choice="a"),
            entry("d2", "decision", "decision about logging", choice="b"),
            entry("d3", "decision", "decision about supersession", choice="c"),
            entry("d4", "decision", "decision about routing", choice="d"),
        ]
        rendered = build_context(projected(records), query="decision supersession", ledger="repo")
        self.assertIn("### d3 ", rendered)
        self.assertNotIn("### d1 ", rendered)
        self.assertIn("d1 decision", rendered)

    def test_a_term_in_every_record_carries_no_weight(self):
        records = [
            entry("d1", "decision", "decision about caching", choice="a"),
            entry("d2", "decision", "decision about logging", choice="b"),
        ]
        self.assertEqual(_term_weights(projected(records), "decision"), {})

    def test_same_inputs_at_one_revision_are_byte_identical(self):
        records = [
            entry("d1", "decision", "Renderer budget", choice="y", scope=("lib/**",)),
            entry("c2", "claim", "A premise", state="accepted"),
        ]
        history = projected(records)
        first = build_context(history, files=("lib/x.py",), ledger="repo")
        second = build_context(history, files=("lib/x.py",), ledger="repo")
        self.assertEqual(first, second)

    def test_header_names_the_latest_record_and_the_real_selection(self):
        records = [entry("c1", "claim", "A premise", state="accepted")]
        rendered = build_context(projected(records), ledger="repo")
        self.assertIn("| latest: c1", rendered)
        self.assertIn("no task scope given", rendered)

    def test_retired_records_stay_out_of_both_tiers(self):
        records = [
            entry("c1", "claim", "Old premise", state="accepted"),
            entry("c2", "claim", "Current premise"),
            entry("c3", "claim", "Retire old", state="accepted", supersedes=("c1",)),
        ]
        rendered = build_context(projected(records), query="Current", ledger="repo")
        self.assertNotIn("Old premise", rendered)


if __name__ == "__main__":
    unittest.main()
