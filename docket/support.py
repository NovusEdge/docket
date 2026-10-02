"""Whether a record's declared grounds still stand.

A citation follows supersessions to the head of its chain. The reason on each
supersession decides what the citing record keeps: a restatement keeps it
clean, a revision flags it for review, a reversal removes the ground. The
model and its proofs are in experiments/lean-outcomes/STRESS-TESTS.md, section 7.
"""

from __future__ import annotations

REASONS = ("restate", "revise", "reverse")
# A missing reason costs a review flag and never hides one.
DEFAULT_REASON = "revise"
