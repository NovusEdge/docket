# docket

A decision ledger for long-running agent work.

An agent settles dozens of small questions during a long task. Those answers stay
in prose. Compaction removes the prose. Twenty steps later the agent contradicts a
decision it already made, and nothing detects this.

docket records decisions so they stay made. Each entry is `settled`, `ruled-out`,
or `open`. Reopening a settled decision retracts the decisions that depend on it.

## Status

Phase 1 works: record and recall, with no enforcement. The remaining five phases
are in [docs/north-star.md](docs/north-star.md).

## Install

```sh
/plugin marketplace add NovusEdge/docket
/plugin install docket@NovusEdge
```

The command lives at `bin/docket`. It needs Python 3.9 or later and no packages.
The session hook prints its absolute path, so nothing has to go on PATH.

For your own shell use, symlink it:

```sh
ln -s ~/Projects/docket/bin/docket ~/.local/bin/docket
```

## Use

```sh
docket add "Which database?" --answer "Postgres via psycopg 3" \
  --cost "migration rewrite if reversed after schema lands"

docket add "Use an ORM?" --state ruled-out --answer "No. Raw SQL for the FTS queries."

docket add "Which async driver?" --answer "asyncpg" --because d1

docket list --state settled
docket list --find postgres
docket show d3
```

A `SessionStart` hook prints the ledger into context. A project with no ledger
costs nothing.

## Where the ledger lives

By default, under `~/.claude/docket/`, keyed by the project's path. Nothing to
create, nothing to gitignore.

```sh
docket where    # print which file is in use
docket init     # move it into the repository as .docket/
```

`docket init` is how a team commits and shares decisions. Existing entries move
with it. A `.docket/ledger.jsonl` in the project always wins over the global
store.

The project is identified by its git root, so a subdirectory shares the same
ledger. `DOCKET_HOME` relocates the global store, and `CLAUDE_CONFIG_DIR` is
honoured so an isolated Claude profile keeps its own.

Run the tests with `python3 tests/test_docket.py`.

## Documents

**[docs/decision-chains.md](docs/decision-chains.md)** — what the literature says
about making agent decisions durable, and which parts of the obvious design it
rules out. Synthesizes five reviews across roughly 40 papers.

**[docs/definitions.md](docs/definitions.md)** — the formal vocabulary. Every
other document defers to it.

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
