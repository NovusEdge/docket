# Lean Outcomes Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Check the intended/unintended partition and an intent counterexample in Lean, with a runnable backup example.

**Architecture:** A single Lean file holds the definitions, proofs, and a small console demonstration. The realization relation and intent labels are explicit inputs; the example does not infer them from real file operations.

**Tech Stack:** Lean 4.33.1 and its bundled standard library, managed by the existing elan installation.

**Spec:** The approved conversation proposal: define steps, chains, outcomes, and intent; prove the partition; check identical behavior with different intent labels. The source notation is in `../../docs/outcome-formalism.md`.

## Global constraints

- Keep all experiment files in `/home/novusedge/Projects/docket/experiments/lean-outcomes/`. Another agent is implementing the ledger in the shared repository.
- Do not change branches, shared project files, or the other agent's work.
- Keep the research documents intact. This experiment covers outcome classification only.
- Use a project toolchain pin; do not change elan's global default.
- Use complete checked proofs, with no admitted goals or custom axioms.
- Use no external Lean packages, LLM calls, or actual file-copy operations.

## Task 1: Establish the toolchain

Files: create `lean-toolchain`.

- [x] Inspect the research notes, Git state, and installed elan toolchains.
- [x] Install `leanprover/lean4:v4.33.1` and record that exact string in `lean-toolchain`.
- [x] Run `lean --version` and verify the selected compiler.

## Task 2: Check the formal claims

Files: create `Outcomes.lean` in this experiment directory.

The mathematical interface is:

```lean
abbrev Chain (Step : Type) := List Step
abbrev Realization (Step Outcome : Type) := Chain Step → Outcome → Prop
abbrev Intent (Step Outcome : Type) := Chain Step → Outcome → Prop
```

For inputs `realizes`, `intends`, `chain`, and `outcome`, define intended
outcomes as `realizes chain outcome ∧ intends chain outcome`, and unintended
outcomes as `realizes chain outcome ∧ ¬ intends chain outcome`.

- [x] State the partition and disjointness theorems with unfinished proof goals; run Lean and observe the unsolved goals.
- [x] Complete both proofs. Use case analysis on whether the outcome is intended.
- [x] Add two backup chains and two outcomes: backup creation and overwriting an old backup. Check many-to-one and one-to-many witnesses.
- [x] Check the same overwrite chain under backup-only and replacement intentions. Prove that the overwrite outcome changes classification while the realization relation stays fixed.
- [x] Add a console demonstration that prints realized, intended, and unintended outcomes for these cases.

## Task 3: Verify and explain the experiment

Files: create `README.md` in this experiment directory.

- [x] Run `lean Outcomes.lean` and `lean --run Outcomes.lean` from this directory.
- [x] Inspect proof axiom dependencies and confirm there are no admitted proofs or custom axioms.
- [x] Explain the example, commands, one small edit to try, and the difference between checked mathematics and measured agent behavior.
- [x] Review the final diff and mark this plan complete.

## Verification

- `lean -DwarningAsError=true Outcomes.lean` succeeds with eight checked theorems.
- `lean --run Outcomes.lean` prints the three backup cases.
- The general partition theorem uses Lean's standard classical foundations. The other seven theorems have no axiom dependencies.
- Changing `backupOnlyIntent` to include overwriting makes `overwrite_is_unintended` fail, as the guide predicts. This check used an in-memory copy of the source.
- All experiment files are confined to this directory.
