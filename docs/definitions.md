# Definitions

This file defines the formal vocabulary. Other design documents use these
definitions.

When a definition changes, record the change in Docket. Then, update each
document that uses the definition.

## Primitives

**Step.** A single action or reasoning move. `S` is the set of steps.

**Claim.** A proposition asserted or derived during the work. `Γ` is the set of
claims.

**Outcome.** A change that persists after the chain that produced it ends. `O` is
the set of outcomes.

An outcome is one of two kinds.

- A **world outcome** changes something outside the agent. Examples include a
  written file, an inserted row, a service call, and a pushed branch. Tool-call
  logs and filesystem state show these outcomes.
- An **epistemic outcome** changes the recorded knowledge. Examples include a
  settled question, a rejected option, and a false assumption. Docket records
  these outcomes.

The collection method is different for each kind. The system computes world
outcomes and records declared epistemic outcomes.

An agent report is not sufficient evidence for a world outcome. Use tool-call
logs and filesystem state as the evidence.

The two kinds also differ in reversibility. World outcomes range from a scratch
file to a force push. Epistemic outcomes are almost always cheap to reverse.
Escalation thresholds therefore bite mostly on world outcomes.

## Chains

**Chain.** A finite sequence of steps directed at an outcome. `C ⊆ S*`.

A decomposed chain is no longer a sequence. Expanding one step into sub-steps
produces a tree, or a directed acyclic graph when sub-steps share support. Any
notation that admits decomposition must admit this.

## The realization relation

**Realization.** `R ⊆ C × O`. The pair `(c, o) ∈ R` means the chain `c` realizes
the outcome `o`.

`R` is a relation, not a function.

- `R(c) = { o ∈ O : (c, o) ∈ R }` is the set of outcomes one chain realizes.
- `R⁻¹(o) = { c ∈ C : (c, o) ∈ R }` is the set of chains that realize one outcome.

Three cardinality cases follow.

**One-to-one.** The assumed default case.

**Many-to-one.** `|R⁻¹(o)| > 1`. Several chains realize the same outcome. This is
outcome non-uniqueness.

**One-to-many.** `|R(c)| > 1`. One chain realizes several outcomes. Side effects
live here.

## Intent

**Intent.** `ι : C → 2^O`. The outcomes a chain aimed at.

The formalism receives `ι` as an input. It does not derive `ι` from `R`.
Different intent relations can classify the same chain and realized outcomes
differently.

Given `ι`:

- **Intentional outcomes** of `c` are `R(c) ∩ ι(c)`.
- **Unintentional outcomes** of `c` are `R(c) \ ι(c)`.

Intentional and unintentional outcomes do not form an independent structural
axis. The classification follows from `R` and `ι`.

## Direct and indirect

**Consequence operator.** `Cl : 2^O → 2^O`. The closure of a set of outcomes under
consequence.

- **Direct outcomes** of `c` are `R(c)`.
- **Indirect outcomes** of `c` are `Cl(R(c)) \ R(c)`.

Specify `Cl` independently before you classify indirect outcomes. Generic closure
laws do not constrain the indirect set.

A useful operator can follow paths in a fixed logical, causal, or transition
relation. Each indirect outcome then has a path from a direct outcome.

Do not confuse this with instrumental and terminal goals. Instrumental and
terminal classify desired outcomes. Direct and indirect classify realized outcomes.

## Claims and justification

**Justification.** `j : Γ → 2^(2^Γ)`. Each claim maps to a set of alternative
justification sets. Each inner set is one complete, independent support for the
claim.

- A claim `γ` is **atomic** when `j(γ) = ∅`. It is a premise that the work asserts.
- A claim `γ` is **reasoned** when it has at least one non-empty justification
  set.

A flat set of premises, `j(γ) = {A}`, is the single-alternative case. It is not
a separate rule.

This structure extends a truth maintenance system with alternative support.
Withdrawing an atomic premise makes that premise unavailable. The change can
make reasoned claims unavailable in turn.

Retain a reasoned claim while one complete justification set survives. Retract
the claim when no complete justification set survives. Retain other atomic
claims unless the work withdraws them explicitly.

Treating atomic claims as self-evident is foundationalism. It is an assumption,
not a result. The regress it answers is real: every reasoned claim needs support,
that support needs support, and the chain terminates, loops, or continues without
end.

## Decomposition

**Reasoning index.** `k ⊆ {1, ..., n}` indexes the steps of a chain that require
reasoning.

**Decomposition limit.** `d` bounds how far a step indexed by `k` expands into
sub-steps.

Intent and effort set the budget `d`. This budget stops the decomposition.

A value-of-information test gives a stronger rule. Expand a step only when a
different answer can change the final outcome.

## Dependency and parallelism

**Dependency.** `≺` is a strict partial order on steps. Read `s_i ≺ s_j` as "step
`s_j` depends on step `s_i`".

**Section.** A contiguous subsequence of a chain.

**Parallel-valid.** A partition into sections is parallel-valid when the state
transformations of every pair of sections commute.

An absent crossing dependency does not establish parallel validity. Consider two
sections with one step in each section:

- The first step sets the state to 1.
- The second step doubles the state.

Declare no dependency between the steps. The empty relation is a strict partial
order, but the two schedules return 2 and 1.

The relation `≺` certifies parallel validity only if it contains every pair of
steps that do not commute.

Step-level commutativity is sufficient. If all cross-section step pairs commute,
the two section transformations also commute.

The Lean proofs check the counterexample and this lift in
`experiments/lean-outcomes/StressTests.lean`.

A partition that is not parallel-valid produces compositional incoherence: each
section computes correctly and the composition does not.

## Ledger states

The implementation records three states for a decision.

- **settled** - The decision applies to later work.
- **ruled-out** - The work rejected this option.
- **open** - The question does not have an answer.

The proposed action gate maps these states to `allow`, `deny`, and `ask`. The
current ledger does not enforce this mapping.

**Supersession.** An entry keeps its recorded state because the log is
append-only. A later entry can name the IDs that it retires.

A retired entry remains in the history but is no longer current. State records
the decision. Supersession records whether the decision remains current.

## Terms deliberately not defined here

**Correctness** of an outcome. The formalism describes realized outcomes and intent.
It does not judge either one.

**Cost.** The ledger records a cost-if-wrong string for human reading. The ledger
does not define a metric. People currently judge escalation thresholds.
