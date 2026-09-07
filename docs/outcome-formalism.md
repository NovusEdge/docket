# A formalism for outcomes, chains, and claims

September 2026. These working notes define the formalism for a proposed paper.
They also identify required prior art and unresolved claims.

## Objects

Let `S` be a set of steps. Let `O` be a set of outcomes. Let `Γ` be a set of
claims.

A chain is a finite sequence of steps. Write `C ⊆ S*` for the set of chains.

The realization relation is `R ⊆ C × O`. The pair `(c, o) ∈ R` means the chain
`c` realizes the outcome `o`.

Write `R(c) = { o ∈ O : (c, o) ∈ R }` for the outcomes a chain realizes.

Write `R⁻¹(o) = { c ∈ C : (c, o) ∈ R }` for the chains that realize an outcome.

## The taxonomy reduces to `R` and `ι`

`R` is a relation, not a function. The proposed distinctions describe its
cardinality and one labeling function.

**Many-to-one.** `|R⁻¹(o)| > 1`. Several chains realize the same outcome. This is
outcome non-uniqueness.

**One-to-many.** `|R(c)| > 1`. One chain realizes several outcomes. This is where
side effects live.

**Intent.** Define `ι : C → 2^O`, the outcomes a chain aimed at. Then:

- Intentional outcomes of `c` are `R(c) ∩ ι(c)`.
- Unintentional outcomes of `c` are `R(c) \ ι(c)`.

Intentional and unintentional outcomes do not form a third structural axis. The
classification follows from `R` and `ι`.

This representation is complete for each exhaustive and disjoint binary
partition of `R(c)`. Choose the intended class as `ι(c)` to reconstruct both
classes. This result does not derive `ι` from `R`.

**Direct and indirect.** Let `Cl : 2^O → 2^O` be a consequence operator. Then:

- Direct outcomes of `c` are `R(c)`.
- Indirect outcomes of `c` are `Cl(R(c)) \ R(c)`.

Generic closure laws do not give this distinction a fixed meaning. Extensivity,
monotonicity, idempotence, and preservation of the empty set are insufficient.

Specify `Cl` independently through a fixed logical, causal, or transition
relation. Require a consequence path from a direct outcome to each indirect
outcome.

## Claims and justification

Each step has supporting claims. Define a justification function
`j : Γ → 2^(2^Γ)`.

The function maps each claim to alternative justification sets. Each inner set
is one complete support for the claim.

- A claim `γ` is **atomic** when `j(γ) = ∅`.
- A claim `γ` is **reasoned** when it has a non-empty justification set.

This structure extends a truth maintenance system with alternative support
(Doyle 1979; de Kleer 1986).

When an atomic premise becomes unavailable, propagate that change through the
support relation. Retain each reasoned claim while one complete justification
set survives. Retain other atomic claims unless the work withdraws them explicitly.

The regress problem applies. Every reasoned claim needs support. That support
needs support. The chain terminates at atomic claims, loops, or continues without
end. Treating atomic claims as self-evident is foundationalism, and it is an
assumption, not a result. State it as one.

## Decomposition

Let `k ⊆ { 1, ..., n }` index the steps of a chain that require reasoning.

Let `d` be a decomposition limit. Each step indexed by `k` expands into at most
`d` sub-steps.

Two consequences follow.

**A decomposed chain is no longer a sequence.** Expansion produces a tree. It
produces a directed acyclic graph when sub-steps share support.

The notation must admit this structure. `C ⊆ S*` is too weak when `d > 1`.

**`d` is a budget, not a constant.** The user's intent and effort level set this
budget. It gives a practical stopping rule.

A value-of-information test gives a stronger rule. Expand a step only when a
different answer can change the final outcome.

## Sections and parallelism

Let `≺` be a dependency relation on steps. Read `s_i ≺ s_j` as "step `s_j`
depends on step `s_i`". Assume `≺` is a strict partial order.

A section is a contiguous subsequence of the chain. A partition is
**parallel-valid** when every pair of section transformations commutes.

An absent crossing edge does not prove this property. The dependency relation
must include every pair of steps that do not commute.

Step-level commutativity is sufficient. If all cross-section step pairs commute,
the complete section transformations also commute.

When transformations do not commute, each section can be locally correct while
their composition changes with the schedule. This is compositional incoherence
(2605.30335).

One result argues against wide parallelism. A single long chain can search an
exponentially larger space than the same compute spent on many short parallel
chains (2505.21825). The paper must address this.

## Prior art the paper must cite

**Intention.** Ward, MacDermott, Belardinelli, Toni, and Everitt, "The Reasons
that Agents Act: Intention and Instrumental Goals" (2402.07221, AAMAS 2024). This
defines intention formally in structural causal influence models. It separates
intended outcomes from foreseen but unintended ones by a counterfactual
criterion. Read it in full. If the definition here does not diverge mechanically
from theirs, this section renames their work.

Philosophical sources: Anscombe on intention and foresight, Bratman's planning
theory, and the doctrine of double effect. "On Automating the Doctrine of Double
Effect" (IJCAI 2017) gives a computational treatment.

**Side effects.** The impact-measure literature already separates
objective-relevant impact from side effect. This is the direct and indirect
distinction under other names. See Krakovna et al. on stepwise relative
reachability (1806.01186) and on future tasks (2010.07877), and Turner et al. on
attainable utility preservation (1902.09725). The critique is 2101.12509.

This work is native to reinforcement learning and gridworlds. No formal treatment
of impact measures exists for LLM and tool-using agents. That absence is where a
novelty claim survives. Claim the application, not the concept.

**Outcome multiplicity.** Self-consistency (2203.11171) exploits many-to-one as a
confidence signal and is the paper a reviewer raises first. Argumentation theory
calls the structure convergent arguments and argument accrual. Classical planning
calls it top-k and top-quality planning (2404.01503), with plan equivalence as the
formal apparatus. No work treats multiplicity as a named taxonomic axis. This is
the strongest novelty claim of the three, and it still requires citing and
distinguishing self-consistency.

**Adjacent and easily confused.** Instrumental and terminal goals classify desired
outcomes. Direct and indirect outcomes classify realized outcomes. Readers can
conflate them. Add a footnote.

**Evaluation precedent.** Agent benchmark surveys already separate outcome-level
success from step-level process metrics, and some score trajectory harms
alongside task success (2507.21504, 2605.16282). This is the applied form of the
taxonomy, implemented as two scores rather than stated as a formalism.

## Open problems this formalism does not solve

Answer order is irrelevant when all answer transformations commute. For two
transformations, order invariance holds exactly when they commute.

Real systems do not always satisfy this condition. Option order changes some
benchmark results by up to 75 percent (2308.11483). Premise order also changes
results on deductive tasks (2502.04134).

Deciding that a claim is atomic is itself a reasoning step, and it can be wrong.
There is no ground truth for self-evidence.

A visible chain often fails to reflect the computation that produced the answer
(2503.08679, 2606.13603). A formalism over stated chains therefore describes what
the system reports, not what it computed.

## Verification limits

Several citations here came from search summaries, not from direct paper reads.
Check any citation before it carries weight. Read 2402.07221 directly, because
the novelty claim for the intention section depends on its exact definition.
