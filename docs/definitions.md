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

This `j` relation is the formal outcome model. It is not the schema 2
`supports` field and it does not describe an automatic runtime retraction rule.
Implemented `supports` records declared grounds, can target a claim or a
decision, and carries no entailment or automatic truth-maintenance behavior.

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

Schema 2 has three record types. Type answers what a line is; state answers what
was recorded about that type; currentness answers whether the line remains in the
current view. These dimensions are independent.

**Claim.** A proposition represented by `text`. Its recorded state is
`unassessed`, `accepted`, `disputed`, or `rejected`. Acceptance is a workflow
judgment. It does not establish truth, validate its evidence, or propagate truth
to another claim.

**Decision.** A commitment represented by `text` and a required `choice` from
`alternatives`. Its recorded state is `adopted` or `revoked`. An adopted
decision is a commitment available to later work, not a claim that the choice is
correct.

**Question.** An unresolved inquiry represented by `text`. Its recorded state is
always `open`. A current accepted claim or applicable adopted decision can
resolve a question through an `answers` link in the derived view. The original
question line and recorded state remain unchanged.

**Recorded state.** The state written on the append-only line. It is preserved
when another record supersedes that line.

**Effective state.** The state shown by a derived view after applying
supersession, applicability, and question-resolution rules. A view exposes both
recorded and effective state when they differ. A decision may remain recorded as
`adopted` while being blocked by an unavailable prerequisite; a blocked decision
does not resolve a question.

**Currentness.** A record is current when no later same-kind record supersedes
it. A retired record remains retrievable history. Its `retired_by` field names
the record that retired it. Retiring a replacement does not revive its
predecessor.

**Supersession.** A later record names same-kind IDs in `supersedes`. This
retires those records permanently in derived current views without deleting or
rewriting their history. Supersession does not revoke dependents automatically.

The action gate described in the research documents is future behavior. The
ledger records typed states and relationships; it does not enforce an
`allow`/`deny`/`ask` mapping.

An adopted decision is **applicable** when its `depends_on` claims are accepted
and current and its `depends_on` decisions are adopted, current, and themselves
applicable. Otherwise a derived view exposes the unavailable prerequisite IDs
in `blocked_by`. This is a derived usability result. It does not revoke the
recorded choice or propagate truth.

## Record fields and relationships

Every schema 2 record contains `schema`, `kind`, `id`, `text`, `state`, `ts`,
`author`, `session`, and `branch`. IDs use `c`, `d`, or `q` followed by a
positive integer. Allocation uses the next global sequence across all types.

The common optional fields are `scope`, `rationale`, `supports`, `depends_on`,
`answers`, `supersedes`, `evidence`, `revisit`, `cost_if_wrong`, and `pinned`.
They have empty defaults, except `pinned`, which defaults to false. Decisions
also have `choice` and `alternatives`.

`supports` stores declared grounds as a list of nonempty ID lists. IDs in one
inner list are conjunctive AND requirements. Inner lists are alternative OR
sets. For example, `[["c1", "c2"], ["c3"]]` means `(c1 AND c2) OR c3`.
The relation is a recorded support formula, not a verified logical implication.
Support targets are claims or decisions. Docket does not automatically
propagate state or enumerate transitive support sets.

`depends_on` is a separate operational relation. Only decisions may use it;
its targets are claims or decisions. It records prerequisites for using a
commitment and never means an alternative justification. Do not collapse it
into `supports`.

`answers` links a current claim or decision to an earlier question. Only claims
and decisions may answer questions. `evidence` contains objects with a required
nonempty `ref` and optional `checked_at` and `commit` strings. Evidence records
provenance supplied by the recorder. It does not claim that the reference was
freshly checked. `revisit` and `cost_if_wrong` record conditions and consequences
for human review.

All relations refer to earlier existing records. The validator rejects unknown
IDs, self-links, duplicate IDs, invalid shapes, invalid states, and invalid
cross-type relations. History and recorded state remain available; current and
resolved views are derived.

## Terms deliberately not defined here

**Correctness** of an outcome. The formalism describes realized outcomes and intent.
It does not judge either one.

**Cost.** The ledger records a cost-if-wrong string for human reading. The ledger
does not define a metric. People currently judge escalation thresholds.
