"""Whether a record's declared grounds still stand.

A citation follows supersessions to the head of its chain. The reason on each
supersession decides what the citing record keeps: a restatement keeps it
clean, a revision flags it for review, a reversal removes the ground. The
model and its proofs are in experiments/lean-outcomes/STRESS-TESTS.md, section 7.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REASONS = ("restate", "revise", "reverse")
# A missing reason costs a review flag and never hides one.
DEFAULT_REASON = "revise"

UNSUPPORTED, FLAGGED, CLEAN = 0, 1, 2
NAMES = {UNSUPPORTED: "unsupported", FLAGGED: "flagged", CLEAN: "clean"}
INHERITED = ("flagged", "blocked")
_SURFACED_STATES = ("accepted", "adopted")


def head_of(
    ident: str, retired: Mapping[str, str], reason_of: Mapping[str, str]
) -> tuple[str, list[str]]:
    """The current record a citation resolves to, and the reasons crossed on the way.

    Docket refuses to supersede a retired record, so each record has at most one
    successor and the walk ends.
    """
    crossed: list[str] = []
    while ident in retired:
        ident = retired[ident]
        crossed.append(reason_of.get(ident, DEFAULT_REASON))
    return ident, crossed


def surfaced(entry: Mapping[str, Any], status: str) -> bool:
    """Whether a projected record shows ``status`` to a reader."""
    return (
        entry.get("support") == status
        and not entry.get("retired_by")
        and entry.get("recorded_state", entry.get("state")) in _SURFACED_STATES
    )


def evaluate(
    entries: list[dict[str, Any]],
    retired: Mapping[str, str],
    applicable: Mapping[str, bool],
) -> dict[str, dict[str, Any]]:
    """Support status for every claim and decision in folded ``entries``."""
    by_id = {entry["id"]: entry for entry in entries}
    reason_of = {entry["id"]: entry.get("supersede_reason", DEFAULT_REASON) for entry in entries}
    graded = [entry for entry in entries if entry["kind"] in ("claim", "decision")]
    circular: set[str] = set()
    pins = {
        entry["id"]: {
            (ground, head)
            for review in entry.get("reviews", [])
            for ground, head in review["grounds"].items()
        }
        for entry in graded
    }

    def ground(owner: str, cited: str, level: Mapping[str, int]) -> tuple[int, str, str]:
        head, crossed = head_of(cited, retired, reason_of)
        target = by_id[head]
        value, because = CLEAN, ""
        for applies, to, why in (
            ("reverse" in crossed, UNSUPPORTED, "reverse"),
            (target["state"] in ("rejected", "revoked"), UNSUPPORTED, target["state"]),
            (level.get(head) == UNSUPPORTED, UNSUPPORTED, "unsupported"),
            (head in circular, FLAGGED, "circular"),
            ("revise" in crossed, FLAGGED, "revise"),
            (target["state"] in ("unassessed", "disputed"), FLAGGED, target["state"]),
            (target["kind"] == "decision" and applicable.get(head) is False, FLAGGED, "blocked"),
            (level.get(head) == FLAGGED, FLAGGED, "flagged"),
        ):
            if applies and to < value:
                value, because = to, why
        # A flag inherited from the head's own flag or block lives at the head,
        # and a head that was never superseded never moves, so a pin there
        # would waive every later cause for good. `because` names only the
        # first cause, so a pin lifts the owned causes and re-tests these two.
        # A circular head sits at FLAGGED but is an owned cause, not inherited.
        if value == FLAGGED and (cited, head) in pins[owner]:
            value, because = CLEAN, ""
            if target["kind"] == "decision" and applicable.get(head) is False:
                value, because = FLAGGED, "blocked"
            elif level.get(head) == FLAGGED and head not in circular:
                value, because = FLAGGED, "flagged"
        return value, head, because

    def prerequisites(entry: Mapping[str, Any]) -> list[tuple[str, str]]:
        """Revised prerequisites the decision has not reviewed; reversals block instead."""
        owed = []
        for cited in entry.get("depends_on", []):
            head, crossed = head_of(cited, retired, reason_of)
            if (
                "revise" in crossed
                and "reverse" not in crossed
                and (cited, head) not in pins[entry["id"]]
            ):
                owed.append((cited, head))
        return owed

    def record_level(entry: Mapping[str, Any], level: Mapping[str, int]) -> int:
        value = CLEAN
        if entry["supports"]:
            value = max(
                min(ground(entry["id"], cited, level)[0] for cited in group)
                for group in entry["supports"]
            )
        if prerequisites(entry):
            value = min(value, FLAGGED)
        return value

    def fixed_point(start: int) -> dict[str, int]:
        level = {entry["id"]: start for entry in graded}
        changed = True
        while changed:
            changed = False
            for entry in graded:
                new = record_level(entry, level)
                if new != level[entry["id"]]:
                    level[entry["id"]] = new
                    changed = True
        return level

    # Support that only the least fixed point denies is circular: nothing
    # grounds it, but nothing withdrew it either, so it is flagged, not lost.
    low, high = fixed_point(UNSUPPORTED), fixed_point(CLEAN)
    circular.update(ident for ident in low if low[ident] != high[ident])
    level = {ident: FLAGGED if ident in circular else low[ident] for ident in low}
    # A review pin lifts a circular ground only when ground() sees it as
    # FLAGGED, which the two fixed points cannot, so clear reviewed records
    # from the frontier of the cycle upward.
    changed = True
    while changed:
        changed = False
        for entry in graded:
            if entry["id"] in circular and record_level(entry, level) == CLEAN:
                level[entry["id"]] = CLEAN
                circular.discard(entry["id"])
                changed = True

    result: dict[str, dict[str, Any]] = {}
    for entry in graded:
        status = level[entry["id"]]
        owed: list[dict[str, str]] = []
        lost: list[dict[str, str]] = []
        sets = [
            [(cited, *ground(entry["id"], cited, level)) for cited in group]
            for group in entry["supports"]
        ]
        for values in sets:
            worst = min(value for _, value, _, _ in values)
            for cited, value, head, because in values:
                if status == FLAGGED and worst == FLAGGED and value == FLAGGED:
                    item = {"ground": cited, "head": head, "because": because}
                    if item not in owed:
                        owed.append(item)
                if status == UNSUPPORTED and value == UNSUPPORTED:
                    item = {"ground": cited, "because": because}
                    if item not in lost:
                        lost.append(item)
        if status == FLAGGED:
            for cited, head in prerequisites(entry):
                item = {"ground": cited, "head": head, "because": "revise"}
                if item not in owed:
                    owed.append(item)
        result[entry["id"]] = {"support": NAMES[status], "review_owed": owed, "lost_grounds": lost}
    return result
