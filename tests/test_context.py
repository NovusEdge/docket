import unittest
import re

from lib.docket_context import build_context, build_delta, _term_weights, _blocking_paths
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
        # File scope with no query: an explicit query outranks a scope, and
        # test_an_explicit_query_outranks_a_file_scope covers that case.
        rendered = build_context(projected(records), files=("app/db/models.py",), ledger="repo")
        self.assertLess(rendered.index("### d3 "), rendered.index("### d2 "))
        self.assertNotIn("### c1 ", rendered)
        self.assertNotIn("### c4 ", rendered)
        self.assertIn("c1 claim", rendered)
        self.assertIn("c4 claim", rendered)
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
        # c2 outranks c1 on recency, so it takes the single full-text slot.
        self.assertIn("A second long premise", rendered)
        self.assertNotIn("### c1 ", rendered)
        self.assertIn("c1", rendered)
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
        for invalid in (511, 0, -1, "900", True, 900.5):
            with self.assertRaises(ValueError):
                build_context(history, max_chars=invalid)
        # None asks for the default target, which task matches may exceed.
        self.assertTrue(build_context(history, max_chars=None))
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

    def test_index_line_states_kind_and_state(self):
        records = [
            entry("d1", "decision", "Use Postgres", choice="postgres", scope=("storage",)),
            entry("c2", "claim", "A premise", state="accepted"),
        ]
        rendered = build_context(projected(records), query="storage", ledger="repo")
        line = next(l for l in rendered.splitlines() if l.startswith("c2 "))
        self.assertTrue(line.startswith("c2 claim accepted  A premise"))

    def test_index_detail_follows_the_score(self):
        long_text = "A premise whose text runs a long way past any clip point at all, going on and on"
        records = [
            entry("c1", "claim", long_text, state="accepted"),
            entry("c2", "claim", long_text, state="accepted"),
            entry("d3", "decision", "Use Postgres", choice="postgres", scope=("storage",)),
        ]
        rendered = build_context(projected(records), query="postgres", ledger="repo")
        older = next(l for l in rendered.splitlines() if l.startswith("c1 "))
        newer = next(l for l in rendered.splitlines() if l.startswith("c2 "))
        self.assertGreater(len(newer), len(older))
        self.assertTrue(older.endswith("..."))

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
        # d3 holds the rare term; the others share only the common one.
        self.assertLess(rendered.index("### d3 "), rendered.index("### d1 "))
        self.assertLess(rendered.index("### d3 "), rendered.index("### d2 "))

    def test_a_term_in_every_record_carries_little_weight(self):
        common = [
            entry("d1", "decision", "decision about caching", choice="a"),
            entry("d2", "decision", "decision about logging", choice="b"),
        ]
        rare = common + [entry("c3", "claim", "supersession", state="accepted")]
        # Present everywhere: worth something on a tiny ledger, and less as the
        # ledger grows. Zero would make a focused query match nothing.
        self.assertEqual(_term_weights(projected(common), "decision"), {"decision": 333})
        weights = _term_weights(projected(rare), "decision supersession")
        self.assertLess(weights["decision"], weights["supersession"])

    def test_a_focused_query_matches_a_focused_ledger(self):
        records = [
            entry("c1", "claim", "Postgres handles the write path", state="accepted"),
            entry("c2", "claim", "Postgres holds the billing rows", state="accepted"),
            entry("d3", "decision", "Use Postgres everywhere", choice="postgres"),
        ]
        rendered = build_context(projected(records), query="postgres", ledger="repo")
        self.assertEqual(rendered.count("### "), 3)
        self.assertNotIn("No task matches", rendered)

    def test_expansion_admits_neighbours_in_score_order(self):
        records = [
            entry("c1", "claim", "Older premise", state="accepted"),
            entry("c2", "claim", "Newer premise", state="accepted"),
            entry("d3", "decision", "Renderer budget", choice="y", scope=("lib/**",),
                  supports=(("c1",), ("c2",))),
        ]
        rendered = build_context(projected(records), files=("lib/render.py",), ledger="repo")
        self.assertLess(rendered.index("### c2 "), rendered.index("### c1 "))

    def test_expansion_stops_below_the_score_floor(self):
        records = [
            entry("c1", "claim", "Distant premise", state="accepted"),
            entry("d2", "decision", "Renderer budget", choice="y", scope=("lib/**",),
                  supports=(("c1",),)),
        ]
        rendered = build_context(projected(records), files=("lib/render.py",),
                                 ledger="repo", max_chars=1000)
        self.assertIn("### d2 ", rendered)
        self.assertLessEqual(len(rendered), 1000)

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
        self.assertRegex(rendered, r"\| latest: c1@[0-9a-f]{12}")
        self.assertIn("no task scope given", rendered)

    def test_admission_survives_a_large_ledger(self):
        # Every context fixture here holds a handful of records, which hid a
        # collapse: the admission gate charged the full index against each
        # candidate, so past about 150 records nothing after the first was
        # admitted.
        records = [entry(f"c{n}", "claim", f"Premise {n} about area{n % 6}",
                         state="accepted", scope=(f"area{n % 6}/**",))
                   for n in range(1, 201)]
        history = projected(records)
        self.assertGreater(build_context(history, all_records=True,
                                         ledger="repo").count("### "), 20)
        self.assertGreater(build_context(history, files=("area1/x.py",),
                                         ledger="repo").count("### "), 20)

    def test_a_long_file_scope_is_identified_by_digest(self):
        records = [entry("c1", "claim", "A premise", state="accepted")]
        many = tuple(f"src/module_{n}/file.py" for n in range(20))
        rendered = build_context(projected(records), files=many, ledger="repo")
        self.assertRegex(rendered, r"# files: 20 paths, [0-9a-f]{8}: ")
        same = build_context(projected(records), files=many, ledger="repo")
        other = build_context(projected(records), files=many[:-1], ledger="repo")
        self.assertEqual(rendered, same)
        self.assertNotEqual(rendered, other)

    def test_an_explicit_query_outranks_a_file_scope(self):
        records = [
            entry("d1", "decision", "Unrelated renderer decision", choice="x",
                  scope=("lib/**",)),
            entry("d2", "decision", "Supersession semantics", choice="y",
                  scope=("docs/**",)),
        ]
        rendered = build_context(projected(records), query="supersession",
                                 files=("lib/render.py",), ledger="repo")
        self.assertLess(rendered.index("### d2 "), rendered.index("### d1 "))

    def test_an_exact_file_scope_outranks_an_incidental_query_word(self):
        records = [
            entry("d1", "decision", "Renderer budget rule", choice="x",
                  scope=("lib/render.py",)),
            entry("c2", "claim", "The installer mentions the cache in passing",
                  state="accepted", scope=("installer/**",)),
        ]
        rendered = build_context(projected(records), query="cache",
                                 files=("lib/render.py",), ledger="repo")
        # The query beats a glob scope. It must not beat the record scoped to
        # the file in hand, even with the full recency bonus added.
        self.assertLess(rendered.index("### d1 "), rendered.index("### c2 "))

    def test_degree_map_counts_every_inbound_relation_once(self):
        from lib.docket_context import _degree_map
        records = [
            entry("c1", "claim", "A premise", state="accepted"),
            entry("c2", "claim", "Another premise", state="accepted"),
            entry("d3", "decision", "Uses both", choice="x",
                  supports=(("c1", "c2"),), depends_on=("c1",)),
            entry("d4", "decision", "Uses one", choice="y", supports=(("c1",),)),
        ]
        degrees = _degree_map(projected(records))
        # d3 names c1 through supports and depends_on; _relation_ids
        # de-duplicates, so it counts once.
        self.assertEqual(degrees["c1"], 2)
        self.assertEqual(degrees["c2"], 1)
        self.assertEqual(degrees.get("d4", 0), 0)

    def test_index_caps_and_counts_the_remainder(self):
        from lib.docket_config import merge
        records = [entry(f"c{n}", "claim", f"Premise {n}", state="accepted")
                   for n in range(1, 101)]
        settings = merge({"index": {"max_lines": 10}})
        rendered = build_context(projected(records), ledger="repo", settings=settings)
        listed = [l for l in rendered.splitlines() if re.match(r"^c\d+ claim ", l)]
        self.assertEqual(len(listed), 10)
        self.assertIn("more; docket list", rendered)

    def test_the_capped_index_keeps_the_highest_scoring_records(self):
        from lib.docket_config import merge
        records = [entry(f"c{n}", "claim", f"Premise {n}", state="accepted")
                   for n in range(1, 101)]
        settings = merge({"index": {"max_lines": 5}})
        rendered = build_context(projected(records), ledger="repo", settings=settings)
        listed = [int(n) for n in re.findall(r"^c(\d+) claim ", rendered, re.M)]
        full = [int(n) for n in re.findall(r"^### c(\d+) ", rendered, re.M)]
        # Recency is the only live component here, so the index holds the newest
        # records the full-text tier could not fit.
        self.assertEqual(len(listed), 5)
        self.assertLess(max(listed), min(full))
        self.assertNotIn("c1 claim", rendered)

    def test_every_record_is_accounted_for_in_the_footer(self):
        records = [
            entry("c1", "claim", "Old premise", state="accepted"),
            entry("c2", "claim", "Current premise", state="accepted"),
            entry("c3", "claim", "Retire old", state="accepted", supersedes=("c1",)),
            entry("d4", "decision", "Uses the old premise", choice="x",
                  depends_on=("c1",)),
        ]
        rendered = build_context(projected(records), query="premise",
                                 ledger="repo", max_chars=900)
        counts = re.search(r"full text: (\d+); index: (\d+); retired: (\d+)", rendered)
        self.assertIsNotNone(counts)
        self.assertEqual(sum(int(value) for value in counts.groups()), 4)

    def test_a_cited_retired_record_still_reaches_the_briefing(self):
        records = [
            entry("c1", "claim", "Old premise", state="accepted"),
            entry("c2", "claim", "Replacement", state="accepted", supersedes=("c1",)),
            entry("d3", "decision", "Cites the old premise", choice="x",
                  scope=("lib/**",), supports=(("c1",),)),
        ]
        rendered = build_context(projected(records), files=("lib/x.py",), ledger="repo")
        # A retired record carries no score, so expansion must reach it through
        # the parent's decayed score.
        self.assertIn("### c1 ", rendered)
        self.assertIn("historical", rendered)

    def test_retired_records_stay_out_of_both_tiers(self):
        records = [
            entry("c1", "claim", "Old premise", state="accepted"),
            entry("c2", "claim", "Current premise"),
            entry("c3", "claim", "Retire old", state="accepted", supersedes=("c1",)),
        ]
        rendered = build_context(projected(records), query="Current", ledger="repo")
        self.assertNotIn("Old premise", rendered)

    def test_blocking_path_names_the_chain_and_the_reason(self):
        records = [
            entry("c1", "claim", "The premise is unproven", state="disputed"),
            entry("d2", "decision", "Trust it", choice="trust", depends_on=("c1",)),
            entry("d3", "decision", "Serve from it", choice="serve",
                  scope=("lib/**",), depends_on=("d2",)),
        ]
        rendered = build_context(projected(records), files=("lib/cache.py",), ledger="repo")
        self.assertIn("blocked: d2 -> c1 disputed", rendered)

    def test_blocking_path_names_retirement_rather_than_recorded_state(self):
        records = [
            entry("c1", "claim", "Superseded premise", state="accepted"),
            entry("c2", "claim", "Replacement", state="accepted", supersedes=("c1",)),
            entry("d3", "decision", "Depends on the old premise", choice="x",
                  scope=("lib/**",), depends_on=("c1",)),
        ]
        rendered = build_context(projected(records), files=("lib/cache.py",), ledger="repo")
        # c1's effective state is still "accepted"; the reason it cannot be used
        # is that c2 retired it.
        self.assertIn("blocked: c1 retired", rendered)

    def test_blocking_path_stops_on_a_cycle(self):
        records = [
            entry("c1", "claim", "Premise", state="disputed"),
            entry("d2", "decision", "First", choice="a", depends_on=("c1",)),
        ]
        by_id = {r["id"]: dict(r) for r in projected(records)}
        # Validation forbids a cycle, so no real ledger contains one. Build it
        # by hand to prove the walk terminates anyway.
        by_id["d2"]["depends_on"] = ["c1", "d2"]
        self.assertEqual(_blocking_paths("d2", by_id), [["c1"]])

    def test_blocking_chain_is_admitted_before_an_unrelated_neighbour(self):
        records = [
            entry("c1", "claim", "The cache is reliable", state="disputed"),
            entry("c2", "claim", "An unrelated supporting premise", state="accepted"),
            entry("d3", "decision", "Serve from the cache", choice="serve",
                  scope=("lib/**",), depends_on=("c1",), supports=(("c2",),)),
        ]
        rendered = build_context(projected(records), files=("lib/cache.py",), ledger="repo")
        self.assertIn("### c1 ", rendered)
        self.assertLess(rendered.index("### c1 "), rendered.index("### c2 "))
        self.assertIn("[blocking prerequisite]", rendered)

    def test_coverage_reports_no_matches(self):
        records = [entry("c1", "claim", "A premise", state="accepted")]
        rendered = build_context(projected(records), query="nothing matches this",
                                 ledger="repo")
        self.assertIn("# Coverage: no matches found", rendered)

    def test_coverage_reports_covered(self):
        records = [
            entry("c1", "claim", "The premise is unproven", state="disputed"),
            entry("d2", "decision", "Serve from it", choice="serve",
                  scope=("lib/**",), depends_on=("c1",)),
        ]
        rendered = build_context(projected(records), files=("lib/cache.py",), ledger="repo")
        self.assertIn("# Coverage: task matches and their prerequisites covered", rendered)

    def test_coverage_reports_partial_when_a_task_match_is_index_only(self):
        records = [
            entry("d1", "decision", "First", choice="a", scope=("lib/**",),
                  rationale="x" * 900),
            entry("d2", "decision", "Second", choice="b", scope=("lib/**",),
                  rationale="y" * 900),
        ]
        # 2200 admits one 900-character record and refuses the second, so one
        # task match reaches the index only. 1400 refuses both.
        rendered = build_context(projected(records), files=("lib/cache.py",),
                                 ledger="repo", max_chars=2200)
        self.assertIn("# Coverage: partial, 1 in the index only", rendered)


class DeltaTests(unittest.TestCase):
    def test_delta_names_added_and_newly_unavailable_records(self):
        records = [
            entry("c1", "claim", "The cache is reliable", state="accepted"),
            entry("d2", "decision", "Serve from the cache", choice="serve",
                  depends_on=("c1",)),
            entry("c3", "claim", "Replace the premise", state="accepted",
                  supersedes=("c1",)),
        ]
        delta = build_delta(projected(records), since="d2",
                            baseline=projected(records[:2]), ledger="repo")
        self.assertIn("### c3 ", delta)
        self.assertIn("since: d2", delta)
        # c1 retired and d2 lost its prerequisite, so both changed. Assert on
        # the record block: a bare "d2" also matches the header's "since: d2".
        self.assertIn("### d2 ", delta)
        self.assertIn("2 no longer available", delta)

    def test_delta_omits_a_record_that_was_never_available(self):
        records = [
            entry("c1", "claim", "A disputed premise", state="disputed"),
            entry("c2", "claim", "A settled premise", state="accepted"),
            entry("c3", "claim", "A later premise", state="accepted"),
        ]
        delta = build_delta(projected(records), since="c2",
                            baseline=projected(records[:2]), ledger="repo")
        self.assertIn("c3", delta)
        # c1 was disputed before the baseline and is disputed now. Nothing
        # changed about it, so it is not part of the delta.
        self.assertNotIn("### c1 ", delta)
        self.assertIn("0 no longer available", delta)

    def test_delta_is_none_for_an_unknown_baseline(self):
        records = [entry("c1", "claim", "A premise", state="accepted")]
        self.assertIsNone(build_delta(projected(records), since="d99",
                                      baseline=[], ledger="repo"))

    def test_delta_refuses_a_baseline_whose_digest_no_longer_matches(self):
        records = [
            entry("c1", "claim", "A premise", state="accepted"),
            entry("c2", "claim", "Another premise", state="accepted"),
        ]
        history = projected(records)
        rendered = build_context(history, ledger="repo")
        token = re.search(r"latest: (c\d+@[0-9a-f]+)", rendered).group(1)
        self.assertIsNotNone(build_delta(history, since=token,
                                         baseline=projected(records), ledger="repo"))
        # A rebase renumbers the tail, so the same ID covers different history.
        stale = token.split("@")[0] + "@deadbeef"
        self.assertIsNone(build_delta(history, since=stale,
                                      baseline=projected(records), ledger="repo"))


if __name__ == "__main__":
    unittest.main()
