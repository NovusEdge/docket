# A formalism for outcomes, chains, and claims

September 2026. Working notes toward a paper. This note states the formalism, the
prior art it must cite, and the parts that need repair.

## Objects

Let `S` be a set of steps. Let `O` be a set of outcomes. Let `Γ` be a set of
claims.

A chain is a finite sequence of steps. Write `C ⊆ S*` for the set of chains.

The realization relation is `R ⊆ C × O`. The pair `(c, o) ∈ R` means the chain
`c` realizes the outcome `o`.

Write `R(c) = { o ∈ O : (c, o) ∈ R }` for the outcomes a chain realizes.

Write `R⁻¹(o) = { c ∈ C : (c, o) ∈ R }` for the chains that realize an outcome.

## The taxonomy reduces to properties of R

`R` is a relation, not a function. The three proposed distinctions describe its
cardinality plus one labelling function.

**Many-to-one.** `|R⁻¹(o)| > 1`. Several chains realize the same outcome. This is
outcome non-uniqueness.

**One-to-many.** `|R(c)| > 1`. One chain realizes several outcomes. This is where
side effects live.

**Intent.** Define `ι : C → 2^O`, the outcomes a chain aimed at. Then:

- Intentional outcomes of `c` are `R(c) ∩ ι(c)`.
- Unintentional outcomes of `c` are `R(c) \ ι(c)`.

Intentional versus unintentional is therefore not a third structural axis. It
follows from one-to-many plus the intent label. State this reduction explicitly.
It is a stronger result than three independent distinctions.

**Direct and indirect.** Let `Cl : 2^O → 2^O` be a consequence operator. Then:

- Direct outcomes of `c` are `R(c)`.
- Indirect outcomes of `c` are `Cl(R(c)) \ R(c)`.

`Cl` must be specified. Candidates: logical entailment, causal descendants in a
structural model, or reachability in a state-transition system. The choice
determines what the distinction means, so make it early.

## Claims and justification

Each step is backed by claims. Define a justification function
`j : Γ → 2^Γ` mapping a claim to its supporting claims.

- A claim `γ` is **atomic** when `j(γ) = ∅`.
- A claim `γ` is **reasoned** when `j(γ) ≠ ∅`.

This is the premise-and-justification structure of a truth maintenance system
(Doyle 1979). Retraction machinery transfers directly. When a premise is
withdrawn, every claim whose justification depends on it is withdrawn as well.

The regress problem applies. Every reasoned claim needs support. That support
needs support. The chain terminates at atomic claims, loops, or continues without
end. Treating atomic claims as self-evident is foundationalism, and it is an
assumption, not a result. State it as one.

## Decomposition

Let `k ⊆ { 1, ..., n }` index the steps of a chain that require reasoning.

Let `d` be a decomposition limit. Each step indexed by `k` expands into at most
`d` sub-steps.

Two consequences follow.

**A decomposed chain is no longer a sequence.** Expanding a step into sub-steps
produces a tree, or a DAG when sub-steps share support. The notation must admit
this. `C ⊆ S*` is too weak once `d > 1`.

**`d` is a budget, not a constant.** It follows from the user's intent and effort
level. This is a pragmatic stopping rule laid on top of the regress. The
principled alternative: expand a step only while a different answer at that step
would change the final outcome. Classical decision theory calls this value of
information.

## Sections and parallelism

Let `≺` be a dependency relation on steps. Read `s_i ≺ s_j` as "step `s_j`
depends on step `s_i`". Assume `≺` is a strict partial order.

A section is a contiguous subsequence of the chain. A partition into sections is
**parallel-valid** when no dependency crosses a section boundary.

In order-theoretic terms, the sections must be antichains under `≺`, or the
partition must respect a topological order of `≺`.

This replaces "the user defines steps as dependent or independent" with a
checkable condition. A wrong independence claim is exactly the compositional
incoherence failure (2605.30335): each section computes correctly, and the
composition does not.

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

**Adjacent and easily confused.** Instrumental and terminal goals classify what is
wanted. Direct and indirect outcomes classify what is reached. Readers will
conflate them. Add a footnote.

**Evaluation precedent.** Agent benchmark surveys already separate outcome-level
success from step-level process metrics, and some score trajectory harms
alongside task success (2507.21504, 2605.16282). This is the applied form of the
taxonomy, implemented as two scores rather than stated as a formalism.

## Open problems this formalism does not solve

Predicate and step order changes the answer. Option order alone swings results up
to 75 percent on some benchmarks (2308.11483). Premise order costs over 30 percent
on deductive tasks (2502.04134). No general fix exists.

Deciding that a claim is atomic is itself a reasoning step, and it can be wrong.
There is no ground truth for self-evidence.

A visible chain often fails to reflect the computation that produced the answer
(2503.08679, 2606.13603). A formalism over stated chains therefore describes what
the system reports, not what it computed.

## Verification limits

Several citations here came from search summaries, not from direct paper reads.
Check any citation before it carries weight. Read 2402.07221 directly, because
the novelty claim for the intention section depends on its exact definition.
