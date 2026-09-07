# Formalism Stress Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stress-test five claims from the outcome formalism with Lean proofs and counterexamples, then record every checked result in Docket.

**Architecture:** `StressTests.lean` contains five isolated namespaces in the user's priority order. Each section states its assumptions explicitly, proves the strongest valid result, and encodes a finite counterexample when the original claim is too strong. `STRESS-TESTS.md` explains the checked results in plain language.

**Tech Stack:** Lean 4.33.1 with its bundled standard library; the repository's `bin/docket` ledger CLI.

**Spec:** The five-item stress-test request in the 2026-09-06 conversation, building on Docket entry `d1` and `Outcomes.lean`.

## Global constraints

- Keep code and documentation changes inside `experiments/lean-outcomes/`.
- Do not change branches, shared project files, or the other agent's work.
- Introduce no custom axioms and leave no admitted or skipped proof goals.
- Treat counterexamples as results and report them prominently.
- Record each final result through `../../bin/docket add`, with an explicit `--because` dependency.

## Task 1: Reduction completeness

- [x] State a representation theorem for every exhaustive, disjoint binary partition of realized outcomes; run Lean and observe the unfinished goal.
- [x] Prove that choosing the intended class itself as `ι` reconstructs both classes as `R ∩ ι` and `R \\ ι`.
- [x] Prove uniqueness of the classification once `R` and `ι` are fixed.
- [x] Record the result and its scope in Docket as `d5`.

## Task 2: Consequence operators

- [x] Define extensivity, monotonicity, idempotence, and preservation of the empty set.
- [x] Construct a closure operator satisfying all four laws that realizes any desired indirect set for a nonempty direct set.
- [x] Prove the induced indirect set is exactly the chosen set when it is disjoint from the direct set.
- [x] State the additional semantic requirement: a fixed consequence relation with a path witness for every indirect outcome.
- [x] Record the closure-law counterexample as ruled-out entry `d6`.

## Task 3: Parallel validity

- [x] Model sections as state transformations and schedule invariance as commutativity.
- [x] Attempt the partial-order-only theorem and encode a counterexample with no declared dependency but noncommuting effects.
- [x] Prove the repaired theorem: cross-section commutativity makes either sequential schedule equal.
- [x] Encode a crossing-dependency counterexample where the schedules produce different states.
- [x] Record the failed original claim as `d7` and the repaired condition as `d8`.

## Task 4: Retraction

- [x] Define retraction as the least set containing a premise and closed under reverse support edges.
- [x] Prove survivors retain every required direct support.
- [x] Prove minimality against any other removal set with those closure properties.
- [x] Encode an alternative-justification counterexample showing that a flat support set over-retracts if its members mean alternatives rather than joint requirements.
- [x] Record the soundness result as `d9` and the representation limitation as `d10`.

## Task 5: Order invariance

- [x] Define evaluation of state updates and order invariance under permutations.
- [x] Prove pairwise commutativity is sufficient for invariance under any permutation.
- [x] Prove two updates are order invariant exactly when they commute.
- [x] Encode a noncommuting pair whose two answer orders produce different outcomes.
- [x] Record the characterization and counterexample as `d11`.

## Task 6: Documentation and verification

- [x] Write `STRESS-TESTS.md` with the five results, assumptions, failures, and run commands.
- [x] Run Lean with warnings as errors and run the console report.
- [x] Inspect theorem axiom dependencies and scan for admitted proofs or custom axioms.
- [x] Verify every new Docket entry and review the experiment-only diff.

Verification on 2026-09-06: both Lean files compile with warnings as errors, the
stress-test executable prints the expected five-result report, and the source has
22 theorems with no `sorry`, `admit`, custom `axiom`, or `unsafe` declarations.
The axiom audit found only Lean's standard `propext` in four finite-example proofs;
the general theorems and all other examples have no axiom dependencies. Docket
entries `d5` through `d11` were read back with their `because` links intact.
