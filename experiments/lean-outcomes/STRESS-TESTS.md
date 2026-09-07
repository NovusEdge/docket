# Formalism stress tests

These Lean checks test five claims from the outcome formalism. A successful Lean
proof means the conclusion follows from the stated definitions and assumptions.
It does not show that those assumptions describe real agents.

Run the checks from this directory:

```sh
lean -DwarningAsError=true StressTests.lean
lean --run StressTests.lean
```

The first command exits silently with code 0 when every proof is complete. The
second prints the result summary. The source contains 22 checked theorems and no
custom axioms or admitted goals.

## 1. Intended and unintended reduction: passes with a scope condition

Let `R` be the realized outcomes. A valid intended/unintended classification is
a binary partition of `R`:

- Every realized outcome is in one class.
- No outcome is in both classes.
- Neither class contains an unrealized outcome.

For every such partition, choose `ι` to be the intended class. Lean proves:

```text
intended = R ∩ ι
unintended = R \\ ι
```

It also proves that fixing `R` and `ι` fixes both classes uniquely. No valid
binary partition is missing from this representation.

This is a representation theorem. It does not infer `ι`, decide whether an
outcome was intended, or justify the binary classification. Docket records the
result as `d5`, depending on `d1`.

## 2. Consequence operators: closure laws are insufficient

**FAIL:** Extensivity, monotonicity, and idempotence do not make the direct versus
indirect distinction meaningful. Adding `Cl(∅) = ∅` still does not fix it.

For any chosen set `D`, define:

```text
Cl_D(X) = X ∪ D    when X is nonempty
Cl_D(∅) = ∅
```

Lean proves that `Cl_D` satisfies all four laws. For any nonempty direct set
disjoint from `D`, its induced indirect outcomes are exactly `D`. The operator
can therefore encode any desired split.

The repair is semantic rather than another generic closure law. Fix a causal,
logical, or transition relation before classifying outcomes, and define closure
by paths through that relation. Lean proves that this path-generated operator
satisfies the four closure laws and that every indirect outcome has a path from
a different direct outcome. The relation still needs an external interpretation;
choosing it after seeing the desired split would recreate the same problem.

Docket records the failed closure-law claim as ruled-out entry `d6`.

## 3. Parallel validity: dependency edges alone are insufficient

**FAIL:** A strict partial order with no edge crossing a section boundary does
not, by itself, guarantee that the sections compose safely.

The counterexample has two one-step sections and an empty dependency relation:

```text
section A: set the state to 1
section B: double the state
```

The empty relation is a strict partial order and has no crossing dependency.
Applying A then B returns `2`; applying B then A returns `1`. The declared graph
missed a real interaction.

The repaired condition is that transformations from different sections commute
for every initial state. Lean proves that commuting sections produce the same
result in either schedule. It also checks a second model where `A ≺ B` crosses
the boundary and the two schedules again return `2` and `1`.

The graph can certify safe parallelism only if every order-sensitive interaction
appears as a dependency. Docket records the counterexample as `d7` and the repair
as `d8`.

## 4. Retraction: sound for required supports, not alternatives

Represent `j(γ)` as the claims that `γ` requires jointly. Define the removed set
as the least set that:

1. Contains the retracted premise.
2. Removes a claim when one of its required supports is removed.

Lean proves two properties:

- Every surviving claim retains each required direct support.
- This procedure removes no more claims than any other removal set satisfying
  the same two rules.

**FAIL:** A flat support set cannot also mean that its members are alternative
justifications. Suppose either `A` or `B` independently supports `Q`. Retracting
`A` removes `Q` under the rule above even though `B` survives and still supports
it.

Phase 4 must state that `j(γ)` is conjunctive, or change the representation to a
set of justification sets and retain `γ` while any complete justification
survives. Docket records the scoped proof as `d9` and the counterexample as
ruled-out entry `d10`.

## 5. Order invariance: commutativity is the condition

Model each answered sub-question as a state transformation. Lean proves:

- Pairwise commuting transformations give the same result under every
  permutation of the answer schedule.
- For two sub-questions, order invariance holds if and only if their
  transformations commute.

The same set-to-one and double transformations are a counterexample when this
condition fails: the two permutations produce `2` and `1`.

Logical independence is sufficient only when it guarantees this operational
noninterference. Independence of the propositions alone says nothing about how
their answers update shared state. Docket records this characterization as
`d11`, depending on the parallel-composition result `d8`.

## Implications for the paper

The central reduction survives as a clean representation result. The claims
about consequence operators and parallel validity need revision. The retraction
claim needs an explicit conjunctive-support assumption, and order invariance
needs commutative updates rather than an informal independence label.
