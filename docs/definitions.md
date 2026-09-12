# Definitions

This file defines the formal vocabulary. Other design documents use these
definitions.

When a definition changes:

1. Record the change in Docket.
2. Update each document that uses the definition.

## Primitives

| Term | Meaning | Notation |
| --- | --- | --- |
| **Step** | A single action or reasoning move. | $S$ is the set of steps. |
| **Claim** | A proposition asserted or derived during the work. | $\Gamma$ is the set of claims. |
| **Outcome** | A change that persists after the chain that produced it ends. | $O$ is the set of outcomes. |

An outcome is one of two kinds.

- A **world outcome** changes something outside the agent. Examples include a
  written file, an inserted row, a service call, and a pushed branch. Confirm
  each change through the affected system's results or state.
- An **epistemic outcome** changes the recorded knowledge. Examples include a
  settled question, a rejected option, and a false assumption. Docket records
  these outcomes.

The proposed outcome-tracking system collects evidence of world outcomes and
records declared epistemic outcomes. Docket currently implements the typed
ledger and its derived views.

Verify world outcomes through tool results and observed state. A call log shows
that a tool was invoked; external effects require confirmation from the affected
system. An agent's report alone provides insufficient evidence.

The two kinds also differ in reversibility. World outcomes range from a scratch
file to a force push. Epistemic outcomes are almost always cheap to reverse.
Escalation thresholds therefore depend mainly on world outcomes.

## Chains

**Chain.** A finite sequence of steps directed at an outcome.

```math
C \subseteq S^*
```

A decomposed chain is no longer a sequence. Expanding one step into sub-steps
produces a tree, or a directed acyclic graph when sub-steps share support. Any
notation that admits decomposition must admit this.

## The realization relation

**Realization.** The pair below means chain `c` realizes outcome `o`.

```math
\begin{aligned}
R &\subseteq C \times O \\
(c, o) &\in R \Longleftrightarrow c \text{ realizes } o
\end{aligned}
```

Treat `R` as a relation. A chain can realize a set of outcomes. For a chain `c`,
the realized outcomes and, for an outcome `o`, the chains that realize it are:

```math
\begin{aligned}
R(c) &= \{o \in O : (c, o) \in R\} \\
R^{-1}(o) &= \{c \in C : (c, o) \in R\}
\end{aligned}
```

The following properties describe how chains and outcomes relate. Many-to-one
and one-to-many can overlap in a many-to-many relation.

**One-to-one.** The assumed default case.

**Many-to-one.** Several chains realize the same outcome. This is outcome
non-uniqueness.

**One-to-many.** One chain realizes several outcomes. Side effects live here.

The corresponding cardinality conditions are:

```math
\begin{aligned}
\lvert R^{-1}(o) \rvert &> 1 && \text{(many-to-one)} \\
\lvert R(c) \rvert &> 1 && \text{(one-to-many)}
\end{aligned}
```

## Intent

**Intent.** The outcomes a chain aimed at.

```math
\iota : C \to 2^O
```

The formalism receives `ι` as an input. It does not derive `ι` from `R`.
Different intent relations can classify the same chain and realized outcomes
differently.

Given `ι`:

```math
\begin{aligned}
\text{Intentional}(c) &= R(c) \cap \iota(c) \\
\text{Unintentional}(c) &= R(c) \setminus \iota(c)
\end{aligned}
```

Intentional and unintentional outcomes do not form an independent structural
axis. The classification follows from `R` and `ι`.

## Direct and indirect

**Consequence operator.** The closure of a set of outcomes under consequence.

```math
\begin{aligned}
Cl &: 2^O \to 2^O \\
\text{Direct}(c) &= R(c) \\
\text{Indirect}(c) &= Cl(R(c)) \setminus R(c)
\end{aligned}
```

Specify `Cl` independently before you classify indirect outcomes. Generic closure
laws do not constrain the indirect set.

A useful operator can follow paths in a fixed logical, causal, or transition
relation. Each indirect outcome then has a path from a direct outcome.

Do not confuse this with instrumental and terminal goals. Instrumental and
terminal classify desired outcomes. Direct and indirect classify realized outcomes.

## Claims and justification

**Justification.** Each claim maps to a set of alternative justification sets.
Each inner set is one complete, independent support for the claim.

```math
\begin{aligned}
j &: \Gamma \to 2^{2^\Gamma} \\
\gamma \text{ is atomic} &\iff j(\gamma) = \varnothing \\
\gamma \text{ is reasoned} &\iff \exists A \in j(\gamma) : A \ne \varnothing
\end{aligned}
```

An **atomic claim** is a premise that the work asserts. A **reasoned claim** has
at least one non-empty justification set. A flat set of premises,
$j(\gamma) = \{A\}$, uses the same rule with a single alternative.

These definitions leave the empty-support case
$j(\gamma) = \{\varnothing\}$ unclassified.

This structure extends a truth maintenance system with alternative support.
Withdrawing an atomic premise makes that premise unavailable. The change can
make reasoned claims unavailable in turn.

Retain a reasoned claim while one complete justification set survives. Retract
the claim when no complete justification set survives. Retain other atomic
claims unless the work withdraws them explicitly.

This `j` relation is the formal justification model. Schema 2 uses `supports` to
record declared grounds; the field does not describe an automatic runtime
retraction rule. Implemented `supports` can target a claim or a decision and
carries no entailment or automatic truth-maintenance behavior.

Treating atomic claims as self-evident is foundationalism. It is an assumption,
not a result. The regress it answers is real: every reasoned claim needs support,
that support needs support, and the chain terminates, loops, or continues without
end.

## Decomposition

**Reasoning index.** `k` indexes the steps of a chain that require reasoning.

**Decomposition limit.** `d` bounds how far a step indexed by `k` expands into
sub-steps.

```math
k \subseteq \{1, \ldots, n\}
```

Intent and effort set the budget `d`. This budget stops the decomposition.

A value-of-information test gives a stronger rule. Expand a step only when a
different answer can change the final outcome.

## Dependency and parallelism

**Dependency.** `≺` is a strict partial order on steps. Read the relation below
as “step `s_j` depends on step `s_i`.”

```math
s_i \prec s_j
```

**Section.** A contiguous subsequence of a chain.

**Parallel-valid.** A partition into sections is parallel-valid when the state
transformations of every pair of sections commute.

An absent crossing dependency does not establish parallel validity. Consider two
sections with one step in each section. The first step sets the state to 1, and
the second step doubles it:

```math
f_1(x) = 1, \qquad f_2(x) = 2x
```

Declare no dependency between the steps. The empty relation is a strict partial
order. The two schedules return different states:

```math
f_2(f_1(x)) = 2, \qquad f_1(f_2(x)) = 1
```

The relation `≺` certifies parallel validity only if it contains every pair of
steps that do not commute.

Step-level commutativity is sufficient. If all cross-section step pairs commute,
the two section transformations also commute.

The Lean proofs check the counterexample and this lift in
`experiments/lean-outcomes/StressTests.lean`.

A partition that is not parallel-valid produces compositional incoherence: each
section computes correctly and the composition does not.

## Ledger states

Schema 2 has three record types. Type identifies what a line is. Recorded state
identifies the state written about that type. Currentness identifies whether the
line remains in the current view. These dimensions are independent.

### Record types

| Type | Representation | Recorded states |
| --- | --- | --- |
| **Claim** | A proposition in `text` | `unassessed`, `accepted`, `disputed`, `rejected` |
| **Decision** | A commitment in `text`, with a required `choice` from `alternatives` | `adopted`, `revoked` |
| **Question** | An unresolved inquiry in `text` | `open` |

Acceptance is a workflow judgment. It does not establish truth, validate its
evidence, or propagate truth to another claim.

An adopted decision is a commitment available to later work. It does not assert
that the choice is correct.

A current accepted claim or applicable adopted decision can resolve a question
through an `answers` link in the derived view. The original question line and
recorded state remain unchanged.

### Recorded state, effective state, and currentness

**Recorded state.** The state written on the append-only line. It is preserved
when another record supersedes that line.

**Effective state.** The state shown by a derived view. Question resolution can
change this value from `open` to `resolved`; the original value remains in
`recorded_state`. Retirement and decision applicability appear in separate
fields: `retired_by`, `applicable`, and `blocked_by`. An adopted decision with an
unavailable prerequisite stays `adopted` and becomes blocked, preventing it from
resolving a question.

**Currentness.** A record is current when no later same-kind record supersedes
it. A retired record remains retrievable history. Its `retired_by` field names
the record that retired it. Retiring a replacement does not revive its
predecessor.

**Supersession.** A later record names same-kind IDs in `supersedes`. This retires
those records permanently in derived current views without deleting or rewriting
their history. Supersession does not revoke dependents automatically.

### Applicability and action gates

The action gate described in the research documents is future behavior. The
ledger records typed states and relationships; it does not enforce an
`allow`/`deny`/`ask` mapping.

An adopted decision is **applicable** when its `depends_on` claims are accepted
and current and its `depends_on` decisions are adopted, current, and themselves
applicable. Otherwise a derived view exposes the unavailable prerequisite IDs
in `blocked_by`. This is a derived usability result. It does not revoke the
recorded choice or propagate truth.

## Record fields and relationships

### Required fields

Every schema 2 record contains these fields:

- `schema`: schema version.
- `kind`: record type.
- `id`: record identifier.
- `text`: record content.
- `state`: recorded state for the record type.
- `ts`: record timestamp.
- `author`: author metadata.
- `session`: session metadata.
- `branch`: branch metadata.

IDs use `c`, `d`, or `q` followed by a positive integer. Allocation uses the
next global sequence across all types.

### Fields with defaults

Every record also contains these fields. Docket supplies their defaults when
the corresponding CLI options are omitted:

- `scope`: scope for the record.
- `rationale`: reasoning recorded with the record.
- `supports`: declared grounds for a claim or decision.
- `depends_on`: prerequisites for using a decision.
- `answers`: link from a claim or decision to an earlier question.
- `supersedes`: same-kind records retired by this record.
- `evidence`: provenance references supplied by the recorder.
- `revisit`: conditions for human review.
- `cost_if_wrong`: consequences recorded for human review.
- `pinned`: whether the record is pinned; defaults to `false`.

These fields have empty defaults except `pinned`. Decisions also have:

- `choice`: the selected option.
- `alternatives`: the considered options, including the choice.
- `decided_by`: optional attribution of the commitment, separate from the
  recorder in `author`.

### Relationship fields

`supports` stores declared grounds as a list of nonempty ID lists. IDs in one
inner list are conjunctive AND requirements. Inner lists are alternative OR
sets. For example, `[["c1", "c2"], ["c3"]]` means `(c1 AND c2) OR c3`.
The relation records declared support. Its links carry no verified logical
implication.
Support targets are claims or decisions. Docket does not automatically
propagate state or enumerate transitive support sets.

`depends_on` is a separate operational relation. Only decisions may use it; its
targets are claims or decisions. It records prerequisites for using a commitment
and never means an alternative justification. Keep it separate from `supports`.

`answers` links a claim or decision to an earlier question. A current accepted
claim or applicable adopted decision resolves the question in the derived view.
The link remains in history when its source is retired or becomes unavailable.

`evidence` contains objects with a required nonempty `ref` and optional
`checked_at` and `commit` strings. These fields preserve the recorder's account
of the evidence and when it was checked. Docket leaves verification to the
reader. `revisit` and `cost_if_wrong` record conditions and consequences for
human review.

### Validation and derived views

All relations refer to earlier existing records. The validator rejects unknown
IDs, self-links, duplicate IDs, invalid shapes, invalid states, and invalid
cross-type relations. History and recorded state remain available; current and
resolved views are derived.

## Terms deliberately not defined here

**Correctness** of an outcome. The formalism describes realized outcomes and intent.
It does not judge either one.

**Cost.** The ledger records a cost-if-wrong string for human reading. The ledger
does not define a metric. People currently judge escalation thresholds.
