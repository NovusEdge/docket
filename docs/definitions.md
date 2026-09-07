# Definitions

This file holds the formal vocabulary. Every other document defers to it. When a
definition changes here, record the change in the ledger and update the documents
that depend on it.

## Primitives

**Step.** A single action or reasoning move. `S` is the set of steps.

**Claim.** A proposition asserted or derived during the work. `Γ` is the set of
claims.

**Outcome.** A change that persists after the chain that produced it ends. `O` is
the set of outcomes.

An outcome is one of two kinds.

- A **world outcome** changes something outside the agent. A file written, a row
  inserted, a service called, a branch pushed. World outcomes are observable
  without asking the agent. Tool-call logs and filesystem state record them.
- An **epistemic outcome** changes what is known or believed. A question settled,
  an option ruled out, an assumption falsified. The ledger records these.

The two kinds differ in how they are collected. World outcomes are computed.
Epistemic outcomes are declared. This matters because a stated chain of reasoning
often fails to reflect the computation behind an answer, so asking an agent what
it changed is unreliable for world outcomes while being the only option for
epistemic ones.

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

**One to one.** The assumed default. Rarely the real case.

**Many to one.** `|R⁻¹(o)| > 1`. Several chains realize the same outcome. This is
outcome non-uniqueness.

**One to many.** `|R(c)| > 1`. One chain realizes several outcomes. Side effects
live here.

## Intent

**Intent.** `ι : C → 2^O`. The outcomes a chain aimed at.

`ι` is supplied, not derived. Identical chains with identical realized outcomes
can be classified differently under different intent relations, so `R` alone does
not determine the classification. Intent must come from additional structure.

Given `ι`:

- **Intentional outcomes** of `c` are `R(c) ∩ ι(c)`.
- **Unintentional outcomes** of `c` are `R(c) \ ι(c)`.

Intentional versus unintentional is therefore not an independent axis. It follows
from the one-to-many case plus the intent label.

## Direct and indirect

**Consequence operator.** `Cl : 2^O → 2^O`. The closure of a set of outcomes under
consequence.

- **Direct outcomes** of `c` are `R(c)`.
- **Indirect outcomes** of `c` are `Cl(R(c)) \ R(c)`.

`Cl` must be specified before the distinction has content. Logical entailment,
causal descendants in a structural model, and reachability in a transition system
each give it a different meaning.

Do not confuse this with instrumental and terminal goals. Instrumental and
terminal classify what is wanted. Direct and indirect classify what is reached.

## Claims and justification

**Justification.** `j : Γ → 2^(2^Γ)`. Each claim maps to a set of alternative
justification sets. Each inner set is one complete, independent support for the
claim.

- A claim `γ` is **atomic** when `j(γ) = {∅}` or `j(γ) = ∅`. It is a premise,
  asserted rather than derived.
- A claim `γ` is **reasoned** when it has at least one non-empty justification
  set.

A flat set of premises, `j(γ) = {A}`, is the single-alternative case. It is not
a separate rule.

This is the premise-and-justification structure of a truth maintenance system,
extended to alternative support. Retraction follows: withdrawing a premise
withdraws a justification set only when the premise belongs to it. A claim is
retained while at least one of its justification sets survives intact. Only
when every justification set has lost a member does the claim itself retract.

Treating atomic claims as self-evident is foundationalism. It is an assumption,
not a result. The regress it answers is real: every reasoned claim needs support,
that support needs support, and the chain terminates, loops, or continues without
end.

## Decomposition

**Reasoning index.** `k ⊆ {1, ..., n}` indexes the steps of a chain that require
reasoning.

**Decomposition limit.** `d` bounds how far a step indexed by `k` expands into
sub-steps.

`d` is a budget, set by intent and effort. It is a pragmatic stopping rule laid on
top of the regress. The principled alternative expands a step only while a
different answer at that step would change the final outcome, which classical
decision theory calls value of information.

## Dependency and parallelism

**Dependency.** `≺` is a strict partial order on steps. Read `s_i ≺ s_j` as "step
`s_j` depends on step `s_i`".

**Section.** A contiguous subsequence of a chain.

**Parallel-valid.** A partition into sections is parallel-valid when the state
transformations of every pair of sections commute.

An absent crossing dependency does not establish this. Give two sections one step
each, one setting the state to 1 and the other doubling it, and declare no
dependency between them. The empty relation is a strict partial order and no edge
crosses the boundary, yet the two schedules return 2 and 1. `≺` certifies
parallel validity only when every noncommuting pair of steps carries an edge.

Commutativity at the step level is enough. If every step of one section commutes
with every step of the other, the two section transformations commute, so either
schedule reaches the same state. `experiments/lean-outcomes/StressTests.lean`
checks both the counterexample and the lift.

A partition that is not parallel-valid produces compositional incoherence: each
section computes correctly and the composition does not.

## Ledger states

The implementation records three states for a decision.

- **settled** — decided, and binding on later work.
- **ruled-out** — eliminated, with the reason recorded.
- **open** — unresolved, carried forward.

These map onto the three values a `PreToolUse` hook returns: `allow`, `deny`, and
`ask`.

**Supersession.** An entry carries the state it was written with and never loses
it, because the log is append-only. A later entry names the ids it retires. The
retired entry keeps its recorded state and stops counting as current, so a
question answered later stops reading as open. State says what was decided;
supersession says whether that decision is still the live one.

## Terms deliberately not defined here

**Correctness** of an outcome. The formalism describes what was realized and what
was aimed at. It says nothing about whether either was right.

**Cost.** The ledger records a cost-if-wrong string for human reading. No metric
is defined, and escalation thresholds currently rest on judgment.
