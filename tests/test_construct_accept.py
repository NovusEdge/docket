"""Acceptance: staged proposals becoming ledger records."""

import tempfile
import unittest
from pathlib import Path

from docket.construct import accept, schema, stage
from docket.ledger import project, read


def prop(
    anchor,
    kind="decision",
    choice="yes",
    text="The cache evicts on write.",
    date="2026-06-18",
    path="a.md",
    scope=None,
    rationale="because",
):
    return schema.proposal(
        kind=kind,
        text=text,
        choice=choice,
        anchor=anchor,
        rationale=rationale,
        scope=scope or [],
        source={"path": path, "date": date},
    )


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
        self.assertEqual(entries[0]["text"], "The cache evicts on write.")

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

    def test_orders_records_by_the_date_of_their_document(self):
        # Recency scores by numeric id (context.py rank_of), never by ts, so
        # chronological ids are the only thing that makes the signal real.
        stage.write(
            self.staged,
            self.accepted(
                prop("late", text="June", date="2026-06-18", path="b.md"),
                prop("early", text="April", date="2026-04-27", path="a.md"),
                prop("middle", text="May", date="2026-05-06", path="c.md"),
            ),
        )
        accept.run(self.staged, self.ledger)
        self.assertEqual([e["text"] for e in read(self.ledger)], ["April", "May", "June"])

    def test_sorts_an_undated_document_before_every_dated_one(self):
        # An unknown date cannot claim recency it has not established.
        stage.write(
            self.staged,
            self.accepted(
                prop("dated", text="April", date="2026-04-27", path="a.md"),
                prop("none", text="Undated", date=None, path="b.md"),
            ),
        )
        accept.run(self.staged, self.ledger)
        self.assertEqual([e["text"] for e in read(self.ledger)], ["Undated", "April"])

    def test_keeps_a_support_ahead_of_the_record_it_grounds(self):
        # Date order yields to support order: a key has to resolve to an id
        # before the record citing it is written.
        ground = prop(
            "ground", kind="claim", choice="", text="Ground", date="2026-06-18", path="b.md"
        )
        cites = prop("cites", text="Cites", date="2026-04-27", path="a.md")
        cites["supports"] = [[ground["key"]]]
        stage.write(self.staged, self.accepted(cites, ground))
        accept.run(self.staged, self.ledger)
        entries = read(self.ledger)
        self.assertEqual([e["text"] for e in entries], ["Ground", "Cites"])
        self.assertEqual(entries[1]["supports"], [[entries[0]["id"]]])

    def test_dates_the_record_from_its_document(self):
        # A briefing that stamps every constructed record with the run date
        # claims a two-year-old decision was made today.
        stage.write(self.staged, self.accepted(prop("one", date="2026-04-27")))
        accept.run(self.staged, self.ledger)
        self.assertTrue(read(self.ledger)[0]["ts"].startswith("2026-04-27"))

    def test_stamps_an_undated_record_with_the_run_time(self):
        stage.write(self.staged, self.accepted(prop("one", date=None)))
        accept.run(self.staged, self.ledger)
        self.assertTrue(read(self.ledger)[0]["ts"])

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
        stage.write(self.staged, self.accepted(prop("a", path="x.md"), prop("b", path="y.md")))
        accept.run(self.staged, self.ledger, source="x.md")
        self.assertEqual([e["text"] for e in read(self.ledger)], ["The cache evicts on write."])
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
