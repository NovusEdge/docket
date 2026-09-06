# Execution ledger: north star and build order

September 2026. This note describes the full system. It also gives a build order
where each phase is useful on its own.

## Division of labour

`superpowers:brainstorming` handles divergent work. It explores intent, surfaces
requirements, and widens the option space. Keep it.

This system handles convergent work. It records what was decided, holds those
decisions binding, and reports what the work changed.

The two need different shapes. Convergent and divergent reasoning are separable
capabilities, and pipelines that keep them as separate stages outperform pipelines
that force both into one pass (2510.26490, 2506.05128). Splitting the tools
follows that result.

The handoff point is the moment a design is approved. Brainstorming ends there.
The ledger starts there.

## The full system

### 1. The ledger

A persistent record of decisions, stored outside any one session.

Each entry holds:

- `id` — a stable identifier.
- `question` — what was being decided.
- `state` — `settled`, `ruled-out`, or `open`.
- `answer` — the decision.
- `justification` — the entry ids this decision depends on. An empty list marks
  an atomic decision.
- `cost_if_wrong` — what breaks if this is later reversed.
- `timestamp` and `session`.

Storage: JSONL for the append path. Promote to SQLite when the query "what did we
settle about X" needs an index.

The ledger loads at session start. It survives compaction, which is the specific
thing a session cannot do for itself. Summarization flattens causal structure and
destroys the links that record which conclusions depend on which claim
(2602.06052, 2606.11213).

### 2. Retraction

Reopening a settled decision retracts every decision whose justification depends
on it.

This is dependency-directed backtracking from truth maintenance systems (Doyle
1979). The justification field is what makes it possible. Without it, reopening a
decision leaves orphaned conclusions in place.

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

Classical decision theory calls this value of information. It covers a measured
weakness: models score 40 to 50 percent at identifying which missing variable is
load-bearing, while solving the fully specified problem correctly (2503.22674).
They also detect ambiguity and answer anyway instead of asking (2605.25284).

### 5. Parallel validity

Before dispatching parallel work, check that no dependency crosses a boundary.

State the dependency relation as a strict partial order on work items. A partition
is valid only when its sections are antichains under that order. A wrong
independence claim produces the compositional incoherence failure: each section
computes correctly, and the composition does not (2605.30335).

### 6. The gate

A `PreToolUse` hook consults the ledger before an action runs.

The hook returns `allow`, `deny`, or `ask`, which map onto the three ledger states
exactly. The hook runs before the permission-mode check, and a `deny` holds even
under `--dangerously-skip-permissions`.

Escalation threshold: reversibility, not confidence. An action whose mistake costs
a five-line edit proceeds with a logged ruling. An action that deletes data or
writes to a shared branch waits for a human.

Confidence thresholds are provably the wrong rule. Optimal deferral depends on the
expert's error rate as well as the model's (2006.01862).

### 7. Replay and eval mining

Replay: run the walker again and supply the logged answers instead of calling the
model.

Eval mining: export the ledger to Parquet. Each settled decision with a known
outcome becomes a labelled example.

## Build order

Each phase ships something useful. Each phase depends only on those before it.

**Phase 1. Record and recall.**
A JSONL ledger and a skill that loads it at session start. No enforcement, no
retraction. The system only remembers.
This alone fixes the contradiction problem, which is the reason the system exists.

**Phase 2. Intent and side effects.**
Declare intended outcomes before work. Record realized outcomes after. Report the
difference.
Pure prompt discipline. No new code beyond two ledger fields.

**Phase 3. Question pruning.**
Add the value-of-information test before any clarifying question.
Also pure prompt. Measurable against the questions it drops.

**Phase 4. Justification and retraction.**
Add the `justification` field and the retraction walk. Reopening a decision now
withdraws its dependents.
This is the first phase that needs real code, and it is the first that borrows
directly from truth maintenance theory.

**Phase 5. Parallel validity.**
Add the dependency order and the antichain check before parallel dispatch.
Roughly ten lines with networkx.

**Phase 6. The gate.**
Add the `PreToolUse` hook. The ledger now blocks actions that contradict settled
decisions.
Leave this last. It is the only phase that can stop work incorrectly, and it needs
the earlier phases to have earned trust first.

## What this does not fix

A per-call gate cannot see a plan. Most real damage comes from a sequence of
individually harmless actions.

The rate of `open` decisions must stay in a narrow band, and nothing holds it
there. Too few catches nothing. Too many produces rubber-stamping, which the
human-factors literature reports as the normal outcome (2502.10036, 2109.05067).

A clean ledger resembles evidence. The reasoning that produced an entry often
fails to reflect the computation behind it (2503.08679, 2606.13603). The ledger
records what was committed to. It does not record why.

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
