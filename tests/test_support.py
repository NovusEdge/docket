import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import docket.ledger as ledger


def claim(ident, **kwargs):
    kwargs.setdefault("state", "accepted")
    return ledger.make_record(
        "claim", f"Claim {ident} holds.", author="test", record_id=ident, **kwargs
    )


def decision(ident, **kwargs):
    kwargs.setdefault("choice", f"Option {ident}")
    return ledger.make_record(
        "decision", f"Decision {ident} commits.", author="test", record_id=ident, **kwargs
    )


def review(ident, target, grounds):
    return {
        "schema": ledger.SCHEMA,
        "kind": "review",
        "id": ident,
        "reviews": target,
        "grounds": grounds,
        "note": "",
        "ts": "2026-10-02T00:00:00+00:00",
        "author": "test",
        "session": "",
        "branch": "",
    }


def at(entries, ident):
    return next(e for e in ledger.project(entries) if e["id"] == ident)


def chain(reason):
    extra = {} if reason is None else {"supersede_reason": reason}
    return [claim("c1"), claim("c2", supports=[["c1"]]), claim("c3", supersedes=["c1"], **extra)]


class ReasonTests(unittest.TestCase):
    def test_a_premise_is_clean(self):
        record = at([claim("c1")], "c1")
        self.assertEqual(
            (record["support"], record["review_owed"], record["lost_grounds"]), ("clean", [], [])
        )

    def test_restate_keeps_a_dependent_clean(self):
        self.assertEqual(at(chain("restate"), "c2")["support"], "clean")

    def test_revise_flags_a_dependent(self):
        record = at(chain("revise"), "c2")
        self.assertEqual(record["support"], "flagged")
        self.assertEqual(
            record["review_owed"], [{"ground": "c1", "head": "c3", "because": "revise"}]
        )

    def test_a_missing_reason_reads_as_revise(self):
        self.assertEqual(at(chain(None), "c2")["support"], "flagged")

    def test_reverse_removes_the_ground(self):
        record = at(chain("reverse"), "c2")
        self.assertEqual(record["support"], "unsupported")
        self.assertEqual(record["lost_grounds"], [{"ground": "c1", "because": "reverse"}])

    def test_an_alternative_survives_a_reversal(self):
        entries = [
            claim("c1"),
            claim("c2"),
            claim("c3", supports=[["c1"], ["c2"]]),
            claim("c4", supersedes=["c1"], supersede_reason="reverse"),
        ]
        self.assertEqual(at(entries, "c3")["support"], "clean")


class StateTests(unittest.TestCase):
    def ground(self, cited):
        return at([cited, claim("c2", supports=[[cited["id"]]])], "c2")

    def test_unassessed_and_disputed_grounds_flag(self):
        for state in ("unassessed", "disputed"):
            with self.subTest(state=state):
                record = self.ground(claim("c1", state=state))
                self.assertEqual(record["support"], "flagged")
                self.assertEqual(record["review_owed"][0]["because"], state)

    def test_a_rejected_ground_is_lost(self):
        record = self.ground(claim("c1", state="rejected"))
        self.assertEqual(record["lost_grounds"], [{"ground": "c1", "because": "rejected"}])

    def test_a_revoked_ground_is_lost(self):
        entries = [decision("d1", state="revoked"), claim("c2", supports=[["d1"]])]
        self.assertEqual(
            at(entries, "c2")["lost_grounds"], [{"ground": "d1", "because": "revoked"}]
        )

    def test_a_blocked_decision_flags(self):
        entries = [
            claim("c1", state="unassessed"),
            decision("d2", depends_on=["c1"]),
            claim("c3", supports=[["d2"]]),
        ]
        self.assertEqual(at(entries, "c3")["review_owed"][0]["because"], "blocked")


class PropagationTests(unittest.TestCase):
    def transitive(self):
        return [
            claim("c1"),
            claim("c2", supports=[["c1"]]),
            claim("c3", supports=[["c2"]]),
            claim("c4", supersedes=["c1"], supersede_reason="revise"),
        ]

    def test_a_flag_propagates_upward(self):
        record = at(self.transitive(), "c3")
        self.assertEqual(
            record["review_owed"], [{"ground": "c2", "head": "c2", "because": "flagged"}]
        )

    def test_reviewing_the_frontier_clears_its_dependents(self):
        entries = [*self.transitive(), review("c2.r1", "c2", {"c1": "c4"})]
        self.assertEqual([at(entries, i)["support"] for i in ("c2", "c3")], ["clean", "clean"])

    def test_review_reraises_when_head_moves(self):
        entries = [
            *chain("revise"),
            review("c2.r1", "c2", {"c1": "c3"}),
            claim("c5", supersedes=["c3"], supersede_reason="revise"),
        ]
        record = at(entries, "c2")
        self.assertEqual(
            record["review_owed"], [{"ground": "c1", "head": "c5", "because": "revise"}]
        )

    def test_a_review_from_above_never_waives_a_later_flag_of_the_ground(self):
        entries = [
            *self.transitive(),
            review("c3.r1", "c3", {"c2": "c2"}),
            review("c2.r1", "c2", {"c1": "c4"}),
            claim("c5", supersedes=["c4"], supersede_reason="revise"),
        ]
        c2, c3 = at(entries, "c2"), at(entries, "c3")
        self.assertEqual(c2["review_owed"], [{"ground": "c1", "head": "c5", "because": "revise"}])
        self.assertEqual(c3["support"], "flagged")
        self.assertEqual(c3["review_owed"], [{"ground": "c2", "head": "c2", "because": "flagged"}])

    def test_a_review_from_above_never_waives_a_later_block_of_the_ground(self):
        entries = [
            claim("c1"),
            claim("c2"),
            decision("d3", depends_on=["c2"], supports=[["c1"]]),
            claim("c4", supports=[["d3"]]),
            claim("c5", supersedes=["c1"], supersede_reason="revise"),
            review("c4.r1", "c4", {"d3": "d3"}),
            review("d3.r1", "d3", {"c1": "c5"}),
            claim("c6", supersedes=["c2"], supersede_reason="reverse"),
        ]
        self.assertFalse(at(entries, "d3")["applicable"])
        c4 = at(entries, "c4")
        self.assertEqual(c4["support"], "flagged")
        self.assertEqual(c4["review_owed"], [{"ground": "d3", "head": "d3", "because": "blocked"}])

    def test_a_pin_on_a_revised_ground_does_not_lift_the_flag_its_head_carries(self):
        entries = [
            claim("c1"),
            claim("c2"),
            claim("c3", supports=[["c2"]]),
            claim("c4", supports=[["c1"]], supersedes=["c2"], supersede_reason="revise"),
            review("c3.r1", "c3", {"c2": "c4"}),
            claim("c5", supersedes=["c1"], supersede_reason="revise"),
        ]
        c3 = at(entries, "c3")
        self.assertEqual(c3["support"], "flagged")
        self.assertEqual(c3["review_owed"], [{"ground": "c2", "head": "c4", "because": "flagged"}])

    def test_a_pin_on_a_revised_ground_does_not_lift_the_block_its_head_carries(self):
        entries = [
            claim("c1"),
            decision("d2"),
            claim("c3", supports=[["d2"]]),
            decision("d4", depends_on=["c1"], supersedes=["d2"], supersede_reason="revise"),
            review("c3.r1", "c3", {"d2": "d4"}),
            claim("c5", supersedes=["c1"], supersede_reason="reverse"),
        ]
        self.assertFalse(at(entries, "d4")["applicable"])
        c3 = at(entries, "c3")
        self.assertEqual(c3["support"], "flagged")
        self.assertEqual(c3["review_owed"], [{"ground": "d2", "head": "d4", "because": "blocked"}])

    def test_a_pin_on_a_circular_head_does_not_lift_a_block_the_head_also_carries(self):
        entries = [
            claim("c1"),
            claim("c2"),
            decision("d3", depends_on=["c2"]),
            claim("c4", supports=[["c1", "d3"]], supersedes=["c1"], supersede_reason="restate"),
            decision("d5", supports=[["c1"]]),
            claim("c6", state="unassessed"),
            claim("c7", supports=[["d5"], ["c6"]]),
            review("d5.r1", "d5", {"c1": "c4"}),
            claim("c8", supersedes=["c2"], supersede_reason="reverse"),
        ]
        d5 = at(entries, "d5")
        self.assertEqual(d5["support"], "flagged")
        self.assertEqual(d5["review_owed"], [{"ground": "c1", "head": "c4", "because": "flagged"}])

    def cycle(self, reason):
        return [
            claim("c1"),
            claim("c2", supports=[["c1"]]),
            claim("c3", supports=[["c2"]], supersedes=["c1"], supersede_reason=reason),
        ]

    def test_an_ungrounded_cycle_is_flagged_circular(self):
        entries = self.cycle("restate")
        self.assertEqual([at(entries, i)["support"] for i in ("c2", "c3")], ["flagged"] * 2)
        self.assertIn(
            {"ground": "c1", "head": "c3", "because": "circular"}, at(entries, "c2")["review_owed"]
        )

    def test_reviewing_the_cycle_frontier_clears_the_cycle(self):
        entries = [*self.cycle("restate"), review("c2.r1", "c2", {"c1": "c3"})]
        for ident in ("c2", "c3"):
            record = at(entries, ident)
            self.assertEqual((record["support"], record["review_owed"]), ("clean", []))

    def test_a_partial_review_leaves_the_other_circular_ground_owed(self):
        entries = [
            claim("c1"),
            claim("c2"),
            claim("c3", supports=[["c1", "c2"]]),
            claim("c4", supports=[["c3"]], supersedes=["c1", "c2"], supersede_reason="restate"),
            review("c3.r1", "c3", {"c1": "c4"}),
        ]
        record = at(entries, "c3")
        self.assertEqual(record["support"], "flagged")
        self.assertEqual(
            record["review_owed"], [{"ground": "c2", "head": "c4", "because": "circular"}]
        )

    def test_the_repository_cycle_shape_is_flagged(self):
        entries = [
            claim("c1", state="disputed"),
            claim("c2", state="unassessed", supports=[["c1"]]),
            claim("c3", supports=[["c2"]], supersedes=["c1"]),
            decision("d4", supports=[["c1"]]),
        ]
        c3, d4 = at(entries, "c3"), at(entries, "d4")
        self.assertEqual((c3["support"], d4["support"]), ("flagged", "flagged"))
        self.assertEqual(d4["review_owed"], [{"ground": "c1", "head": "c3", "because": "circular"}])
        self.assertEqual((c3["lost_grounds"], d4["lost_grounds"]), ([], []))

    def test_a_real_loss_inside_a_cycle_stays_unsupported(self):
        record = at(self.cycle("reverse"), "c2")
        self.assertEqual(record["support"], "unsupported")
        self.assertEqual(record["lost_grounds"], [{"ground": "c1", "because": "reverse"}])

    def test_a_cycle_member_holds_through_another_set(self):
        entries = [
            claim("c1"),
            claim("c2"),
            claim("c3", supports=[["c1"], ["c2"]]),
            claim("c4", supports=[["c3"]], supersedes=["c1"], supersede_reason="restate"),
        ]
        self.assertEqual(at(entries, "c3")["support"], "clean")

    def test_without_supersession_every_accepted_record_is_clean(self):
        entries = [
            claim("c1"),
            claim("c2", supports=[["c1"]]),
            decision("d3", supports=[["c1", "c2"]]),
            claim("c4", supports=[["d3"], ["c1"]]),
        ]
        self.assertEqual(
            {e["support"] for e in ledger.project(entries) if "support" in e}, {"clean"}
        )


class PrerequisiteTests(unittest.TestCase):
    def prerequisite(self, reason):
        return [
            claim("c1"),
            decision("d2", depends_on=["c1"]),
            claim("c3", supersedes=["c1"], supersede_reason=reason),
        ]

    def test_a_restated_prerequisite_is_followed(self):
        record = at(self.prerequisite("restate"), "d2")
        self.assertEqual((record["applicable"], record["support"]), (True, "clean"))

    def test_a_revised_prerequisite_is_followed_and_flagged(self):
        record = at(self.prerequisite("revise"), "d2")
        self.assertEqual((record["applicable"], record["support"]), (True, "flagged"))
        self.assertEqual(
            record["review_owed"], [{"ground": "c1", "head": "c3", "because": "revise"}]
        )

    def test_a_reversed_prerequisite_blocks(self):
        record = at(self.prerequisite("reverse"), "d2")
        self.assertFalse(record["applicable"])
        self.assertIn("c1", record["blocked_by"])


class ForwardCycleTests(unittest.TestCase):
    def test_a_prerequisite_that_resolves_back_onto_its_dependent_blocks(self):
        entries = [
            decision("d1"),
            decision("d2", depends_on=["d1"]),
            decision("d3", depends_on=["d2"], supersedes=["d1"], supersede_reason="restate"),
        ]
        d2, d3 = at(entries, "d2"), at(entries, "d3")
        self.assertEqual((d2["applicable"], d3["applicable"]), (False, False))
        self.assertIn("d1", d2["blocked_by"])
        self.assertEqual((d2["support"], d3["support"]), ("clean", "clean"))


def random_ledger(rng):
    entries, retired = [], set()
    for number in range(1, rng.randint(3, 12) + 1):
        kind = rng.choice(["claim", "decision"])
        ident = f"{kind[0]}{number}"
        earlier = [e["id"] for e in entries]
        extra = {}
        if earlier:
            extra["supports"] = [
                sorted({rng.choice(earlier) for _ in range(rng.randint(1, 2))})
                for _ in range(rng.choice([0, 1, 1, 2]))
            ]
        if kind == "decision" and earlier and rng.random() < 0.3:
            extra["depends_on"] = [rng.choice(earlier)]
        open_same = [e["id"] for e in entries if e["kind"] == kind and e["id"] not in retired]
        if open_same and rng.random() < 0.35:
            target = rng.choice(open_same)
            extra["supersedes"] = [target]
            extra["supersede_reason"] = rng.choice(["restate", "revise", "reverse"])
        if kind == "claim":
            extra["state"] = rng.choice(
                ["accepted", "accepted", "unassessed", "disputed", "rejected"]
            )
            record = claim(ident, **extra)
        else:
            extra["state"] = rng.choice(["adopted", "adopted", "revoked"])
            record = decision(ident, **extra)
        try:
            ledger.project([*entries, record])
        except ledger.LedgerError:
            continue
        entries.append(record)
        retired.update(extra.get("supersedes", []))
    return entries


class InvariantTests(unittest.TestCase):
    def test_random_ledgers_keep_support_consistent_with_its_evidence(self):
        for seed in range(300):
            rng = random.Random(seed)
            entries = random_ledger(rng)
            for round_ in range(rng.randint(0, 3)):
                for record in ledger.project(entries):
                    if "review_owed" in record and record["review_owed"] and rng.random() < 0.5:
                        owed = {o["ground"]: o["head"] for o in record["review_owed"]}
                        number = sum(1 for e in entries if e["id"].startswith(record["id"] + ".r"))
                        entries.append(review(f"{record['id']}.r{number + 1}", record["id"], owed))
            with self.subTest(seed=seed):
                projected = ledger.project(entries)
                for record in projected:
                    if "support" not in record:
                        continue
                    owed, lost = record["review_owed"], record["lost_grounds"]
                    expected = {
                        "flagged": (True, False),
                        "unsupported": (False, True),
                        "clean": (False, False),
                    }[record["support"]]
                    self.assertEqual((bool(owed), bool(lost)), expected, record["id"])
                self.assertEqual(ledger.project(entries), projected)


class RevisionTests(unittest.TestCase):
    def test_derived_support_fields_stay_out_of_the_revision(self):
        from docket.context_model import _revision

        projected = ledger.project(chain("revise"))
        self.assertIn("support", projected[1])
        bare = [
            {k: v for k, v in e.items() if k not in ("support", "review_owed", "lost_grounds")}
            for e in projected
        ]
        self.assertEqual(_revision(projected), _revision(bare))


if __name__ == "__main__":
    unittest.main()
