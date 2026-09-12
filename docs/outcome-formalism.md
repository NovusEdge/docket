# A formalism for outcomes, chains, and claims

September 2026. These working notes define a formalism for a proposed paper.
They identify prior art the paper must cite and claims that remain unresolved.

## Core objects

| Symbol | Meaning |
| --- | --- |
| `S` | Set of steps. |
| `O` | Set of outcomes. |
| `Γ` | Set of claims. |
| `C` | Set of finite chains. |
| `R` | Relation between chains and outcomes. |
| `ι` | Outcomes a chain aimed at. |

A chain is a finite sequence of steps:

```math
C \subseteq S^*
```

The realization relation connects chains to outcomes. The pair `(c, o) ∈ R`
means that chain `c` realizes outcome `o`:

```math
R \subseteq C \times O
```

For a chain `c` and an outcome `o`, define:

```math
R(c) = \{o \in O : (c,o) \in R\}
```

```math
R^{-1}(o) = \{c \in C : (c,o) \in R\}
```

`R` is a relation. `R(c)` is the set of outcomes realized by one chain, and
`R⁻¹(o)` is the set of chains that realize one outcome.

## Outcome taxonomy

The proposed distinctions describe the cardinality of `R` and one labeling
function. They do not add independent structural axes.

| Distinction | Condition | Interpretation |
| --- | --- | --- |
| Many-to-one | `|R⁻¹(o)| > 1` | Several chains realize the same outcome. This is outcome non-uniqueness. |
| One-to-many | `|R(c)| > 1` | One chain realizes several outcomes. Side effects live here. |
| Intentional | `R(c) ∩ ι(c)` | Realized outcomes the chain aimed at. |
| Unintentional | `R(c) \ ι(c)` | Realized outcomes outside the chain's aim. |
| Direct | `R(c)` | Outcomes directly realized by the chain. |
| Indirect | `Cl(R(c)) \ R(c)` | Consequences added by the specified consequence operator. |

Define intent as the outcomes a chain aimed at:

```math
ι : C \to 2^O
```

Then the intentional and unintentional sets are:

```math
\operatorname{Intentional}(c) = R(c) \cap ι(c)
```

```math
\operatorname{Unintentional}(c) = R(c) \setminus ι(c)
```

For every exhaustive and disjoint binary partition of `R(c)`, choosing the
intended class as `ι(c)` reconstructs both classes. The result does not derive
`ι` from `R`.

Direct and indirect outcomes require a separately specified consequence
operator:

```math
Cl : 2^O \to 2^O
```

Generic closure laws do not determine the meaning of the indirect set.
Extensivity, monotonicity, idempotence, and preservation of the empty set are
insufficient. Specify `Cl` through a fixed logical, causal, or transition
relation, and require a consequence path from a direct outcome to each indirect
outcome.

## Claims and justification

Each step has supporting claims. Each claim can have several alternative
justification sets. Every inner set is one complete support for the claim:

```math
j : \Gamma \to 2^{2^\Gamma}
```

The claim classifications are:

- A claim `γ` is **atomic** when `j(γ) = ∅`.
- A claim `γ` is **reasoned** when it has at least one non-empty justification
  set.

These definitions leave the empty-support case
$j(\gamma) = \{\varnothing\}$ unclassified.

This structure extends a truth maintenance system with alternative support
(Doyle 1979; de Kleer 1986). When an atomic premise becomes unavailable,
propagate that change through the support relation. Retain a reasoned claim
while one complete justification set survives. Retain other atomic claims until
the work withdraws them explicitly.

The regress problem remains. Every reasoned claim needs support, and that support
needs support. The chain terminates at atomic claims, loops, or continues
without end. Treating atomic claims as self-evident is foundationalism. It is an
assumption that the formalism does not establish, and the paper should state it
as one.

## Decomposition

Let `k` index the steps that require reasoning, and let `d` be a decomposition
limit:

```math
k \subseteq \{1, \ldots, n\}
```

Each step indexed by `k` expands into at most `d` sub-steps. The user's intent
and effort level set `d`, so it is a budget and a practical stopping rule.

A decomposed chain has a tree structure. Shared support can turn that tree into
a directed acyclic graph. The sequence notation is therefore too weak when
`d > 1`:

```math
C \subseteq S^*
```

A value-of-information test gives a stronger stopping rule: expand a step only
when a different answer can change the final outcome.

## Sections and parallelism

Let `≺` be a strict partial order on steps. Read `sᵢ ≺ sⱼ` as “step `sⱼ`
depends on step `sᵢ`.” A section is a contiguous subsequence of a chain. A
partition is **parallel-valid** when every pair of section transformations
commutes.

An absent crossing edge does not establish parallel validity. The dependency
relation must include every pair of steps that do not commute. Step-level
commutativity is sufficient: if all cross-section step pairs commute, the
complete section transformations commute.

When transformations do not commute, each section can be locally correct while
the composition changes with the schedule. This is compositional incoherence
(2605.30335).

One result argues against wide parallelism. A single long chain can search an
exponentially larger space than the same compute spent on many short parallel
chains (2505.21825). The paper must address this result.

## Prior art the paper must cite

**Intention.** Ward, MacDermott, Belardinelli, Toni, and Everitt, “The Reasons
that Agents Act: Intention and Instrumental Goals” (2402.07221, AAMAS 2024)
defines intention formally in structural causal influence models. It separates
intended outcomes from foreseen but unintended ones by a counterfactual
criterion. Read it in full. If this definition does not mechanically diverge
from theirs, rename this section's contribution.

Philosophical sources include Anscombe on intention and foresight, Bratman's
planning theory, and the doctrine of double effect. “On Automating the Doctrine
of Double Effect” (IJCAI 2017) gives a computational treatment.

**Side effects.** Impact-measure research provides related prior art for
studying the effects of an agent's actions. Compare its definitions directly
with the direct/indirect and intentional/unintentional classifications here.
See Krakovna et al. on stepwise relative reachability (1806.01186) and future
tasks (2010.07877), and Turner et al. on attainable utility preservation
(1902.09725). The critique is 2101.12509.

Review how these impact measures have already been applied to LLM and
tool-using agents before claiming a contribution in that setting. The current
source review leaves that question open.

**Outcome multiplicity.** Self-consistency (2203.11171) exploits many-to-one as
a confidence signal and is the paper a reviewer is likely to raise first.
Argumentation theory calls the structure convergent arguments and argument
accrual. Classical planning calls it top-k and top-quality planning (2404.01503),
with plan equivalence as the formal apparatus. Whether prior work treats
multiplicity as a named taxonomic axis remains an open literature question.
Any novelty claim requires citing and distinguishing self-consistency.

**Adjacent concepts.** Instrumental and terminal goals classify desired
outcomes. Direct and indirect outcomes classify realized outcomes. Add a
footnote so readers do not conflate them.

**Evaluation precedent.** Agent benchmark surveys already separate outcome-level
success from step-level process metrics, and some score trajectory harms
alongside task success (2507.21504, 2605.16282). This is the applied form of
the taxonomy, implemented as two scores rather than stated as a formalism.

## Open problems

The formalism leaves these questions open:

1. Answer order is irrelevant when all answer transformations commute. For two
   transformations, order invariance holds exactly when they commute:

   ```math
   f_2 \circ f_1 = f_1 \circ f_2
   ```

   Real systems do not always satisfy this condition. Option order changes some
   benchmark results by up to 75 percent (2308.11483), and premise order changes
   results on deductive tasks (2502.04134).
2. Deciding that a claim is atomic is itself a reasoning step and can be wrong.
   There is no ground truth for self-evidence.
3. A visible chain often fails to reflect the computation that produced the
   answer (2503.08679, 2606.13603). A formalism over stated chains therefore
   describes what the system reports; the underlying computation remains
   unverified.

## Verification limits

Several citations came from search summaries rather than direct paper reads.
Check each citation before it carries weight. Read 2402.07221 directly because
the intention-section novelty claim depends on its exact definition.
