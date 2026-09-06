# docket

A decision ledger for long-running agent work.

An agent settles dozens of small questions during a long task. Those answers stay
in prose. Compaction removes the prose. Twenty steps later the agent contradicts a
decision it already made, and nothing detects this.

docket records decisions so they stay made. Each entry is `settled`, `ruled-out`,
or `open`. Reopening a settled decision retracts the decisions that depend on it.

## Status

Design and research only. No implementation yet. The build order is in
[docs/north-star.md](docs/north-star.md).

## Documents

**[docs/decision-chains.md](docs/decision-chains.md)** — what the literature says
about making agent decisions durable, and which parts of the obvious design it
rules out. Synthesizes five reviews across roughly 40 papers.

**[docs/outcome-formalism.md](docs/outcome-formalism.md)** — a formalism for
chains, outcomes, and claims. Treating chains-to-outcomes as a relation rather
than a function reduces a three-part taxonomy to two cardinality properties and
one labelling function.

**[docs/north-star.md](docs/north-star.md)** — the full system, and a build order
where each phase ships something useful on its own.

## Position

Structure imposed on a modern reasoning model mostly buys extra compute. Tree and
graph scaffolds deliver approximately what repeated sampling delivers at the same
token budget. External structure is worth its cost only where it does something
the model cannot do alone.

Persisting a decision across a compaction boundary is one of those things.

## Design commitments

Escalation follows reversibility, not confidence. An action whose mistake costs a
five-line edit proceeds with a logged ruling. An action that deletes data waits
for a human. Confidence thresholds are provably the wrong deferral rule.

The ledger records what was committed to. It does not record why. A visible
reasoning chain often fails to reflect the computation behind the answer, so the
ledger is checkable against later behavior rather than trusted as an explanation.

Decisions are labelled atomic or reasoned. Reasoned decisions carry the entries
they depend on. This is the premise-and-justification structure of a truth
maintenance system (Doyle 1979), which supplies the retraction machinery.

## Open gaps this work targets

Reversibility as the deferral threshold. Deferral theory carries a free
cost-of-error parameter, and nobody has applied blast radius to it.

Deferral where the expert degrades. Machine learning theory models the human as an
oracle with a fixed error rate. Human-factors research shows that deferring
degrades that oracle.

A relevance filter on sub-questions. A question earns its place only when a
different answer changes the final action.

A truth-maintenance-shaped ledger under an agent. No system runs one with a
measured before-and-after comparison.

## Prior art

The documents cite prior art in full. The two to read first: Ward et al. on the
formal definition of intention in causal models (arXiv:2402.07221), and Krakovna
et al. on side effects through relative reachability (arXiv:1806.01186).

## Verification limits

Several citations came from search summaries rather than direct paper reads. Check
any citation before it carries weight.
