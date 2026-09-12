# Execution ledger: north star and build order

September 2026. This note describes the target system and its proposed delivery
order. Each stage should provide useful behavior on its own. The typed ledger and
context walker are shipped in Docket 0.8.0; later stages remain proposed.

## Division of labor

`superpowers:brainstorming` handles divergent work. It explores intent, surfaces
requirements, and widens the option space.

The execution ledger handles convergent work. It records decisions, treats them
as binding, and reports what the work changed.

The tasks need different structures. Convergent and divergent reasoning are
separable capabilities (2510.26490, 2506.05128), and the cited studies report
better results when pipelines separate them. Approval marks the handoff:
brainstorming ends and the ledger starts.

## System map

| Component | Status | Purpose |
| --- | --- | --- |
| Typed ledger | Shipped in 0.8.0 | Persist typed records outside one session. |
| Supersession and derived views | Partly shipped | Record supersession and derive current, resolved, and blocked views. Automatic dependent retraction remains a target. |
| Outcome tracking | Proposed | Compare intended outcomes with realized outcomes. |
| Question pruning | Proposed | Keep questions whose answers can change the final action. |
| Parallel validity | Proposed | Check commutativity before parallel dispatch. |
| Action gate | Proposed | Return `allow`, `deny`, or `ask` before tool execution. |
| Replay and evaluation mining | Proposed | Reuse recorded answers and export labeled outcomes. |

## System components

### 1. Typed ledger

The ledger is a persistent record of decisions stored outside any one session.
Each schema 2 record contains:

- `id`: stable identifier.
- `kind`: `claim`, `decision`, or `question`.
- `text`: proposition, commitment prompt, or inquiry.
- `state`: type-specific recorded state.
- `choice` and `alternatives`: selected choice and options for a decision.
- `supports`: alternative AND sets of supporting record IDs.
- `depends_on`: operational prerequisites for a decision.
- `answers`: links from claims or decisions to questions they resolve.
- `supersedes`: entry IDs that this entry retires.
- `scope`, `rationale`, `evidence`, `revisit`, and `cost_if_wrong`: context and
  review metadata.
- `ts`, `session`, `author`, `branch`, and `pinned`: provenance and retrieval
  fields.

Type, recorded state, and currentness are separate. A claim can be `accepted`
without being true. A decision can be `adopted` without being correct.
Supersession retires a line from current views while preserving its recorded
state and history. A question is resolved by a current accepted claim or
applicable adopted decision that links to it through `answers`. An adopted
decision with unavailable prerequisites remains adopted but is derived as
blocked and cannot resolve a question.

The current command stores append-only JSONL. By default, it stores one ledger
for each Git repository under `~/.claude/docket/`. `docket init` copies existing
entries to `.docket/ledger.jsonl` and makes the project ledger active.

The ledger loads at session start and survives compaction. Summarization
flattens causal structure and destroys the links that record which conclusions
depend on which claims (2602.06052, 2606.11213).

### 2. Supersession and retraction

The current `--supersedes` option retires an earlier entry. History keeps the
retired entry, current lists exclude it, and context can include a cited
historical premise with a warning. Graph and show retain or retrieve history.

Automatic retraction is target behavior. When an entry retires a decision, the
system must examine each dependent justification set:

```math
\text{retain} \iff \exists\text{ complete support set that survives}
```

Retract a dependent decision when no complete support set survives. This
behavior is dependency-directed backtracking from truth maintenance systems
(Doyle 1979). The `supports` field provides declared support links; `depends_on`
records operational prerequisites separately.

### 3. Outcome tracking

Before work starts, declare intended outcomes. After work ends, record realized
outcomes. For chain `c`, the proposed sets are:

```math
\operatorname{Intentional}(c) = R(c) \cap \iota(c)
```

```math
\operatorname{Unintentional}(c) = R(c) \setminus \iota(c)
```

Report the unintentional set. Impact-measure research on reinforcement learning
agents provides related prior art (1806.01186, 1902.09725). Its relationship to
this intent-based classification needs a direct comparison. Establishing what
already applies to tool-using agents remains a research task.

### 4. Question pruning

Before asking a question, test whether a different answer changes the plan. Drop
the question when every answer leaves the final action unchanged.

Classical decision theory calls this value of information. One study measured a
related weakness (2503.22674). Models identified the necessary missing variable
in 40 to 50 percent of tests while solving the fully specified versions. Models
can also detect ambiguity and answer without asking for the missing information
(2605.25284).

### 5. Parallel validity

Before dispatching parallel work, check that section transformations commute. A
dependency relation can certify this property only when it contains every pair
of steps that do not commute.

Write `fᵢ` for a step transformation and `F_A`, `F_B` for the complete
transformations of sections `A` and `B`. Step-level commutativity is sufficient:

```math
\left(\forall s_i \in A, s_j \in B: f_i \circ f_j = f_j \circ f_i\right)
\Rightarrow F_A \circ F_B = F_B \circ F_A
```

A wrong independence claim causes compositional incoherence. Each section can be
locally correct while their composition changes with the schedule (2605.30335).

### 6. Action gate

A proposed `PreToolUse` hook consults the ledger before an action runs. It
returns `allow`, `deny`, or `ask`. These values are a future action policy and do
not correspond one-to-one with typed ledger states. The current Docket hook only
loads the ledger at session start.

The proposed escalation threshold is reversibility. An action whose mistake
costs a five-line edit can proceed with a logged ruling. An action that deletes
data or writes to a shared branch waits for a human. Confidence alone is not a
sufficient threshold; optimal deferral also depends on the expert's error rate
(2006.01862).

### 7. Replay and evaluation mining

Replay runs the walker again and supplies logged answers instead of calling the
model. Evaluation mining exports the ledger to Parquet and uses each applicable
adopted decision with a known outcome as a labeled example.

## Proposed delivery order

Each stage depends on the preceding stages:

1. **Record and recall.** Store decisions outside one session and load current
   decisions when a session starts.
2. **Record support and supersession.** Record alternative support sets and
   retire earlier entries without deleting history.
3. **Retract dependent decisions.** Recalculate support after supersession and
   retract a decision only when no complete support set survives.
4. **Track outcomes.** Record intended outcomes before work, compute realized
   world outcomes after work, and report unintentional outcomes.
5. **Prune questions.** Apply the value-of-information test before a clarifying
   question and drop a question when no answer can change the final action.
6. **Validate parallel work.** Verify cross-section commutativity before
   parallel dispatch. Use the dependency graph only when it contains all
   noncommuting step pairs.
7. **Gate and replay actions.** Add the action gate after reliable support and
   outcome data exist. Add replay and evaluation exports.

## What this does not fix

- A per-call gate cannot see a plan. Most real damage comes from sequences of
  individually harmless actions.
- The rate of open questions must stay in a narrow band, and nothing holds it
  there. Too few catches little. Too many produces rubber-stamping, which the
  human-factors literature reports as the normal outcome (2502.10036,
  2109.05067).
- A clean ledger resembles evidence. The reasoning that produced an entry often
  fails to reflect the computation behind it (2503.08679, 2606.13603). The
  ledger records declared rationale, grounds, and evidence; it does not
  establish faithfulness of the internal computation.
- The ledger only grows. Every surprise adds an entry, and nobody deletes one.
  Schedule a review, as Anthropic recommends tearing down accumulated
  configuration every six months.

## Storage decisions

| Data | Proposed storage and validation |
| --- | --- |
| Graph or schema files | YAML parsed strictly. PyYAML uses YAML 1.1, where unquoted `no`, `on`, and `off` become booleans. Use `strictyaml`, or `ruamel.yaml` in 1.2 mode. Validate with `jsonschema` against draft 2020-12. |
| Ledger | JSONL at runtime. Load into SQLite through the standard library `sqlite3` for queries. Export to Parquet through `pyarrow` for evaluation mining. |
| Graph invariants | Check acyclicity and edge completeness with custom code because no schema language expresses graph-level invariants declaratively. |

## Verification limits

Several citations came from search summaries rather than direct paper reads.
Check any citation before it carries weight.
