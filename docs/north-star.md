# Execution ledger: north star and build order

September 2026. This note describes the target system and its proposed delivery
order. Each stage must provide useful behavior on its own.

## Division of labor

`superpowers:brainstorming` handles divergent work. It explores intent, surfaces
requirements, and widens the option space. Keep it.

This system handles convergent work. It records decisions, treats them as
binding, and reports what the work changed.

The two tasks need different structures. Convergent and divergent reasoning are
separable capabilities (2510.26490, 2506.05128).

The cited studies report better results when pipelines separate these tasks.
This design therefore uses separate tools.

Approval marks the handoff point. Brainstorming ends there. The ledger starts
there.

## The full system

### 1. The ledger

A persistent record of decisions, stored outside any one session.

Each schema 2 record contains:

- `id` - A stable identifier.
- `kind` - `claim`, `decision`, or `question`.
- `text` - The proposition, commitment prompt, or inquiry.
- `state` - Type-specific recorded state.
- `choice` and `alternatives` - The selected choice and options for decisions.
- `supports` - Alternative AND sets of supporting record IDs.
- `depends_on` - Operational prerequisites for decisions.
- `answers` - Links from claims or decisions to questions they resolve.
- `supersedes` - Entry IDs that this entry retires.
- `scope`, `rationale`, `evidence`, `revisit`, and `cost_if_wrong` - Context and
  review metadata.
- `ts`, `session`, `author`, `branch`, and `pinned` - Provenance and retrieval
  fields.

Type, state, and currentness are separate. A claim can be `accepted` without
being true. A decision can be `adopted` without being correct. Supersession
retires a line from current views while preserving its recorded state and
history. A question is resolved by a current accepted claim or applicable adopted
decision that links to it through `answers`. An adopted decision with unavailable
prerequisites remains adopted but is derived as blocked and cannot resolve a
question.

The current command stores append-only JSONL. By default, it stores one ledger
for each Git repository under `~/.claude/docket/`.

The `docket init` command copies existing entries to `.docket/ledger.jsonl`.
It then makes the project ledger active.

The ledger loads at session start. It survives compaction, which is the specific
thing a session cannot do for itself. Summarization flattens causal structure and
destroys the links that record which conclusions depend on which claim
(2602.06052, 2606.11213).

### 2. Supersession and retraction

The current `--supersedes` option retires an earlier entry. The history keeps the
retired entry. The current list excludes it; context can include a cited
historical premise with a warning, while graph and show retain or retrieve it.

Automatic retraction is target behavior. When an entry retires a decision, the
system must examine each dependent justification set.

Retain a dependent decision while one complete justification set survives.
Retract the decision when no complete justification set survives.

This behavior is dependency-directed backtracking from truth maintenance systems
(Doyle 1979). The `supports` field provides declared support links; `depends_on`
records operational prerequisites separately.

### 3. Outcome tracking

Before work starts, declare the intended outcomes. After work ends, record the
realized outcomes.

- Intentional outcomes are the intersection.
- Unintentional outcomes are the difference.

Report the unintentional set. This is the part no current tool does, and it is
where the safety value sits. The impact-measure literature formalizes the same
distinction for reinforcement learning agents (1806.01186, 1902.09725). No
equivalent exists for tool-using agents.

### 4. Question pruning

Before asking a question, test whether a different answer changes the plan. Drop
the question when it does not.

Classical decision theory calls this value of information. One study measured a
related weakness (2503.22674).

Models identified the necessary missing variable in 40 to 50 percent of the
tests. The same models solved the fully specified problems.

Models can also detect ambiguity and answer without asking for the missing
information (2605.25284).

### 5. Parallel validity

Before dispatching parallel work, check that the section transformations
commute.

A dependency relation can certify this property only if it contains every pair
of steps that do not commute. Missing an interaction can change the result.

Step-level commutativity gives a sufficient check. If all cross-section step
pairs commute, the complete section transformations also commute.

A wrong independence claim causes compositional incoherence. Each section can be
locally correct while their composition changes with the schedule (2605.30335).

### 6. The gate

A `PreToolUse` hook consults the ledger before an action runs.

The target hook returns `allow`, `deny`, or `ask`. These values are a future
action policy and do not correspond one-to-one with the typed ledger states.

The target design adds this gate. The current Docket hook only loads the ledger
at session start.

Escalation threshold: reversibility, not confidence. An action whose mistake costs
a five-line edit proceeds with a logged ruling. An action that deletes data or
writes to a shared branch waits for a human.

Confidence alone is not a sufficient threshold. Optimal deferral also depends on
the expert's error rate (2006.01862).

### 7. Replay and eval mining

Replay: run the walker again and supply the logged answers instead of calling the
model.

Eval mining: export the ledger to Parquet. Use each applicable adopted decision with a known
outcome as a labeled example.

## Proposed delivery order

Each stage depends on the preceding stages.

**Stage 1. Record and recall.** Store decisions outside one session. Load current
decisions when a session starts.

**Stage 2. Record support and supersession.** Record alternative support sets.
Retire an earlier entry without deleting its history.

**Stage 3. Retract dependent decisions.** Recalculate support after a
supersession. Retract a decision only when no complete support set survives.

**Stage 4. Track outcomes.** Record intended outcomes before work. Compute
realized world outcomes after work. Report the unintentional outcomes.

**Stage 5. Prune questions.** Apply the value-of-information test before a
clarifying question. Drop a question when no answer can change the final action.

**Stage 6. Validate parallel work.** Verify cross-section commutativity before
parallel dispatch. Use the dependency graph only when it contains all
noncommuting step pairs.

**Stage 7. Gate and replay actions.** Add the action gate after the ledger has
reliable support and outcome data. Add replay and evaluation exports.

## What this does not fix

A per-call gate cannot see a plan. Most real damage comes from a sequence of
individually harmless actions.

The rate of open questions must stay in a narrow band, and nothing holds it
there. Too few catches nothing. Too many produces rubber-stamping, which the
human-factors literature reports as the normal outcome (2502.10036, 2109.05067).

A clean ledger resembles evidence. The reasoning that produced an entry often
fails to reflect the computation behind it (2503.08679, 2606.13603). The ledger
records declared rationale, grounds, and evidence. It does not establish the
faithfulness of the internal computation.

The ledger only grows. Every surprise adds an entry, and nobody deletes one.
Schedule a review, the same way Anthropic recommends tearing down accumulated
configuration every six months.

## Storage decisions

Graph or schema files: YAML, parsed strictly. PyYAML defaults to YAML 1.1, where
unquoted `no`, `on`, and `off` become booleans. Use `strictyaml`, or `ruamel.yaml`
in 1.2 mode. Validate with `jsonschema` against draft 2020-12.

Ledger: JSONL at runtime. Load into SQLite through the standard library `sqlite3`
for queries. Export to Parquet through `pyarrow` for eval mining.

Acyclicity and edge-completeness checks need custom code. No schema language
expresses graph-level invariants declaratively.

## Verification limits

Several citations here came from search summaries, not from direct paper reads.
Check any citation before it carries weight.
