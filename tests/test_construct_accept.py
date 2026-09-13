"""Acceptance: staged proposals becoming ledger records."""

import json
import tempfile
import unittest
from pathlib import Path

from docket.construct import accept, schema, stage
from docket.ledger import project, read


def prop(anchor, kind="decision", choice="yes", text="Question?", date="2026-06-18",
         path="a.md", scope=None, rationale="because"):
    return schema.proposal(kind=kind, text=text, choice=choice, anchor=anchor,
                           rationale=rationale, scope=scope or [],
                           source={"path": path, "date": date})


class AcceptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "ledger.jsonl"
        self.staged = Path(self.tmp.name) / "proposed.jsonl"

    def accepted(self, *items):
        marked = []
        for item in items:
            item = dict(item)
            item["state"] = "accepted"
            marked.append(item)
        return marked

    def test_writes_an_accepted_proposal_to_the_ledger(self):
        stage.write(self.staged, self.accepted(prop("one")))
        accept.run(self.staged, self.ledger)
        entries = read(self.ledger)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], "Question?")

    def test_allocates_a_real_ledger_id(self):
        stage.write(self.staged, self.accepted(prop("one")))
        accept.run(self.staged, self.ledger)
        self.assertEqual(read(self.ledger)[0]["id"], "d1")

    def test_leaves_a_staged_proposal_alone(self):
        stage.write(self.staged, [prop("one")])
        accept.run(self.staged, self.ledger)
        self.assertEqual(read(self.ledger), [])

    def test_leaves_a_rejected_proposal_alone(self):
        item = dict(prop("one"))
        item["state"] = "rejected"
        stage.write(self.staged, [item])
        accept.run(self.staged, self.ledger)
        self.assertEqual(read(self.ledger), [])

    def test_names_the_source_document_in_the_rationale(self):
        # A later reader has to be able to tell a constructed record from one a
        # human wrote at the time.
        stage.write(self.staged, self.accepted(prop("one", path="context/x.md")))
        accept.run(self.staged, self.ledger)
        self.assertIn("context/x.md", read(self.ledger)[0]["rationale"])

    def test_records_the_run_as_the_author(self):
        stage.write(self.staged, self.accepted(prop("one")))
        accept.run(self.staged, self.ledger)
        self.assertEqual(read(self.ledger)[0]["author"], "docket-construct")

    def test_a_second_run_writes_nothing_again(self):
        stage.write(self.staged, self.accepted(prop("one")))
        accept.run(self.staged, self.ledger)
        accept.run(self.staged, self.ledger)
        self.assertEqual(len(read(self.ledger)), 1)

    def test_marks_a_written_proposal_so_it_is_not_written_twice(self):
        stage.write(self.staged, self.accepted(prop("one")))
        accept.run(self.staged, self.ledger)
        self.assertEqual(stage.read(self.staged)[0]["state"], "written")

    def test_accepts_only_the_named_source_when_asked(self):
        stage.write(self.staged, self.accepted(prop("a", path="x.md"),
                                               prop("b", path="y.md")))
        accept.run(self.staged, self.ledger, source="x.md")
        self.assertEqual([e["text"] for e in read(self.ledger)], ["Question?"])
        states = {p["source"]["path"]: p["state"] for p in stage.read(self.staged)}
        self.assertEqual(states, {"x.md": "written", "y.md": "accepted"})

    def test_carries_scope_through(self):
        stage.write(self.staged, self.accepted(prop("one", scope=["src/**"])))
        accept.run(self.staged, self.ledger)
        self.assertEqual(read(self.ledger)[0]["scope"], ["src/**"])


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "ledger.jsonl"
        self.staged = Path(self.tmp.name) / "proposed.jsonl"

    def test_rewrites_a_support_key_into_the_allocated_id(self):
        # Staged edges point at identity keys. The ledger speaks in ids, which
        # only exist once a record is written.
        base = prop("root", kind="claim", choice="")
        child = prop("child")
        child["supports"] = [[base["key"]]]
        for item in (base, child):
            item["state"] = "accepted"
        stage.write(self.staged, [base, child])
        accept.run(self.staged, self.ledger)
        entries = {e["kind"]: e for e in read(self.ledger)}
        self.assertEqual(entries["decision"]["supports"], [[entries["claim"]["id"]]])

    def test_skips_a_record_whose_support_was_not_accepted(self):
        # Writing it with the support quietly dropped would turn a grounded
        # record into a free-standing one. Its grounds are part of what it says.
        base = prop("root", kind="claim", choice="")
        child = prop("child")
        child["supports"] = [[base["key"]]]
        child["state"] = "accepted"
        stage.write(self.staged, [base, child])
        accept.run(self.staged, self.ledger)
        self.assertEqual(read(self.ledger), [])
        self.assertEqual(stage.read(self.staged)[1]["state"], "accepted")

    def test_rewrites_supersedes_into_the_allocated_id(self):
        old = prop("old", date="2026-01-01")
        new = prop("new", date="2026-06-01")
        new["supersedes"] = [old["key"]]
        for item in (old, new):
            item["state"] = "accepted"
        stage.write(self.staged, [old, new])
        accept.run(self.staged, self.ledger)
        entries = sorted(read(self.ledger), key=lambda e: e["id"])
        self.assertEqual(entries[1]["supersedes"], [entries[0]["id"]])

    def test_a_supported_record_is_written_before_the_one_supporting_it(self):
        base = prop("root", kind="claim", choice="")
        child = prop("child")
        child["supports"] = [[base["key"]]]
        for item in (base, child):
            item["state"] = "accepted"
        # Reverse order on the stage; acceptance must still resolve the key.
        stage.write(self.staged, [child, base])
        accept.run(self.staged, self.ledger)
        entries = {e["kind"]: e for e in read(self.ledger)}
        self.assertEqual(entries["decision"]["supports"], [[entries["claim"]["id"]]])

    def test_the_written_ledger_projects_cleanly(self):
        base = prop("root", kind="claim", choice="")
        child = prop("child")
        child["supports"] = [[base["key"]]]
        for item in (base, child):
            item["state"] = "accepted"
        stage.write(self.staged, [base, child])
        accept.run(self.staged, self.ledger)
        self.assertEqual(len(project(read(self.ledger))), 2)


class CrashSafetyTests(unittest.TestCase):
    """A failed append must not leave the stage claiming nothing was written.

    There is no transaction across N appends, so the stage has to record each
    one as it lands. Otherwise the user sees an error, reruns --accept, and
    appends a second copy of everything already written.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "ledger.jsonl"
        self.staged = Path(self.tmp.name) / "proposed.jsonl"

    def three(self):
        items = [dict(prop(f"anchor {i}")) for i in range(3)]
        for item in items:
            item["state"] = "accepted"
        return items

    def test_a_failing_append_leaves_the_earlier_ones_marked_written(self):
        stage.write(self.staged, self.three())
        calls = {"n": 0}
        real = accept.append

        def flaky(ledger, record):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("disk went away")
            return real(ledger, record)

        accept.append = flaky
        try:
            with self.assertRaises(RuntimeError):
                accept.run(self.staged, self.ledger)
        finally:
            accept.append = real

        self.assertEqual(len(read(self.ledger)), 2)
        states = [p["state"] for p in stage.read(self.staged)]
        self.assertEqual(states.count("written"), 2)

    def test_rerunning_after_a_failure_writes_only_what_is_left(self):
        stage.write(self.staged, self.three())
        calls = {"n": 0}
        real = accept.append

        def flaky(ledger, record):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("disk went away")
            return real(ledger, record)

        accept.append = flaky
        try:
            with self.assertRaises(RuntimeError):
                accept.run(self.staged, self.ledger)
        finally:
            accept.append = real

        accept.run(self.staged, self.ledger)
        # Three records total, never five.
        self.assertEqual(len(read(self.ledger)), 3)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "ledger.jsonl"
        self.staged = Path(self.tmp.name) / "proposed.jsonl"

    def test_reports_how_many_records_it_wrote(self):
        items = [prop("a"), prop("b")]
        for item in items:
            item["state"] = "accepted"
        stage.write(self.staged, items)
        written, skipped = accept.run(self.staged, self.ledger)
        self.assertEqual((written, skipped), (2, 0))

    def test_counts_a_record_with_missing_grounds_as_skipped(self):
        base = prop("root", kind="claim", choice="")
        child = prop("child")
        child["supports"] = [[base["key"]]]
        child["state"] = "accepted"
        stage.write(self.staged, [base, child])
        written, skipped = accept.run(self.staged, self.ledger)
        self.assertEqual((written, skipped), (0, 1))


if __name__ == "__main__":
    unittest.main()
