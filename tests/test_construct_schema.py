"""Proposal shape, identity and local validation."""

import unittest

from docket.construct import schema


class NormalizeAnchorTests(unittest.TestCase):
    def test_strips_markdown_emphasis_around_a_label(self):
        # The spike's whole batch-one anchor miss: the model emitted the label
        # without the bold markers the source carries.
        self.assertEqual(
            schema.normalize_anchor("**Decision:** Option B - tiered checking"),
            schema.normalize_anchor("Decision: Option B - tiered checking"),
        )

    def test_strips_inline_code_backticks(self):
        self.assertEqual(
            schema.normalize_anchor("use `build_context` for runs"),
            schema.normalize_anchor("use build_context for runs"),
        )

    def test_keeps_underscores_because_identifiers_carry_them(self):
        # The corpus has 62162 identifier underscores against 9 uses of
        # _emphasis_. Stripping them merges set_timeout with settimeout, and a
        # merged anchor silently collapses two records into one.
        self.assertNotEqual(
            schema.normalize_anchor("set_timeout(x) was removed"),
            schema.normalize_anchor("settimeout(x) was removed"),
        )

    def test_keeps_a_dunder_distinct_from_the_bare_word(self):
        self.assertNotEqual(
            schema.normalize_anchor("`__init__` is generated"),
            schema.normalize_anchor("init is generated"),
        )

    def test_collapses_runs_of_whitespace(self):
        self.assertEqual(
            schema.normalize_anchor("one   two\n\tthree"),
            schema.normalize_anchor("one two three"),
        )

    def test_keeps_distinct_sentences_distinct(self):
        self.assertNotEqual(
            schema.normalize_anchor("Store the ledger in the project"),
            schema.normalize_anchor("Store the ledger globally"),
        )


class IdentityTests(unittest.TestCase):
    def test_same_source_and_anchor_give_the_same_key(self):
        a = schema.identity("context/decisions/auth.md", "**Decision:** use JWT")
        b = schema.identity("context/decisions/auth.md", "Decision: use JWT")
        self.assertEqual(a, b)

    def test_same_anchor_in_a_different_document_differs(self):
        a = schema.identity("context/decisions/auth.md", "Decision: use JWT")
        b = schema.identity("context/devlog/auth.md", "Decision: use JWT")
        self.assertNotEqual(a, b)

    def test_the_separator_cannot_be_forged_from_path_text(self):
        # A key built by plain concatenation would collide here.
        a = schema.identity("a/b", "c")
        b = schema.identity("a", "b/c")
        self.assertNotEqual(a, b)


class ScopeValidationTests(unittest.TestCase):
    def test_accepts_a_path_and_a_glob(self):
        self.assertEqual(schema.invalid_scope(["docket/context.py", "lib/**"]), [])

    def test_rejects_the_prose_paragraph_the_spike_produced(self):
        prose = (
            "This record covers the documents describing the coherence "
            "layer and its storage decisions, " * 8
        ) + "src/**"
        self.assertTrue(len(prose) > 200)
        self.assertEqual(schema.invalid_scope([prose]), [prose])

    def test_rejects_an_entry_carrying_whitespace(self):
        self.assertEqual(schema.invalid_scope(["src/a.py and src/b.py"]), ["src/a.py and src/b.py"])

    def test_rejects_an_empty_entry(self):
        self.assertEqual(schema.invalid_scope([""]), [""])

    def test_reports_every_bad_entry_not_just_the_first(self):
        self.assertEqual(schema.invalid_scope(["", "ok/path.py", "a b"]), ["", "a b"])

    def test_rejects_a_glob_that_matches_the_whole_tree(self):
        # Scope decides which records a briefing surfaces. An entry matching
        # everything makes the record surface in every briefing, which is worse
        # than no scope at all.
        self.assertEqual(schema.invalid_scope(["**"]), ["**"])
        self.assertEqual(schema.invalid_scope(["*"]), ["*"])
        self.assertEqual(schema.invalid_scope(["**/*"]), ["**/*"])

    def test_rejects_an_absolute_path(self):
        # Scope is matched against repository-relative paths, so an absolute one
        # can never match, and it leaks a filesystem layout into the ledger.
        self.assertEqual(schema.invalid_scope(["/etc/passwd"]), ["/etc/passwd"])

    def test_rejects_a_path_climbing_out_of_the_repository(self):
        self.assertEqual(schema.invalid_scope(["../../secrets.env"]), ["../../secrets.env"])

    def test_keeps_a_directory_glob(self):
        self.assertEqual(schema.invalid_scope(["src/**", "docket/cli/*.py"]), [])


class IdentityDiscriminatorTests(unittest.TestCase):
    def test_a_derived_record_keys_apart_from_the_one_it_borrowed_from(self):
        # A contradiction question borrows a record's anchor and source so a
        # reviewer has a line to open. Without a discriminator it keys the same,
        # and acceptance drops one of the two as a duplicate.
        plain = schema.identity("a.md", "Claim: x")
        derived = schema.identity("a.md", "Claim: x", kind="question")
        self.assertNotEqual(plain, derived)

    def test_the_discriminator_is_stable(self):
        self.assertEqual(
            schema.identity("a.md", "Claim: x", kind="question"),
            schema.identity("a.md", "Claim: x", kind="question"),
        )


class ProposalTests(unittest.TestCase):
    def make(self, **over):
        fields = {
            "kind": "decision",
            "text": "The ledger lives in the project.",
            "choice": "In the project",
            "anchor": "**Decision:** in the project",
            "source": {"path": "context/decisions/ledger.md", "date": "2026-06-18"},
        }
        fields.update(over)
        return schema.proposal(**fields)

    def test_carries_the_identity_key_derived_from_source_and_anchor(self):
        p = self.make()
        self.assertEqual(p["key"], schema.identity(p["source"]["path"], p["anchor"]))

    def test_starts_staged(self):
        self.assertEqual(self.make()["state"], "staged")

    def test_defaults_scope_and_confidence(self):
        p = self.make()
        self.assertEqual(p["scope"], [])
        self.assertEqual(p["confidence"], "low")

    def test_rejects_a_kind_the_ledger_does_not_have(self):
        with self.assertRaises(schema.SchemaError):
            self.make(kind="opinion")

    def test_rejects_a_decision_with_no_choice(self):
        with self.assertRaises(schema.SchemaError):
            self.make(choice="")

    def test_a_question_needs_no_choice(self):
        p = self.make(kind="question", choice="")
        self.assertEqual(p["kind"], "question")

    def test_rejects_an_empty_anchor(self):
        # The anchor is the identity key and the reviewer's way back to the
        # source. A record without one cannot be resumed or checked.
        with self.assertRaises(schema.SchemaError):
            self.make(anchor="")

    def test_rejects_an_invalid_scope_entry(self):
        with self.assertRaises(schema.SchemaError):
            self.make(scope=["a b c"])

    def test_a_null_date_is_allowed(self):
        # Pass 1 cannot always resolve one, and pass 2 proposes no supersession
        # edge for a record without it.
        self.assertIsNone(self.make(source={"path": "a.md", "date": None})["source"]["date"])

    def test_a_question_shaped_decision_proposal_is_refused(self):
        with self.assertRaisesRegex(schema.SchemaError, "state the commitment"):
            self.make(text="Which database should we use?")

    def test_a_question_proposal_may_end_in_a_question_mark(self):
        p = self.make(kind="question", choice="", text="Which cache should we use?")
        self.assertEqual(p["text"], "Which cache should we use?")

    def test_a_question_shaped_claim_proposal_is_refused(self):
        with self.assertRaisesRegex(schema.SchemaError, "state the commitment"):
            self.make(kind="claim", choice="", text="Does the cache evict on write?")


if __name__ == "__main__":
    unittest.main()
