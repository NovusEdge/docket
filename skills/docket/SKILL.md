---
name: docket
description: Keep typed claims, decisions, and questions available to later work, with explicit support, prerequisites, provenance, and reversals.
---

# docket

Docket is an append-only schema 2 ledger. It keeps typed records available after
conversation compaction. Read the current context before starting work.

Use the absolute command path supplied by the session context. The examples use
`docket` for readability.

## Record types and states

Use a **claim** for a scoped proposition. Its recorded state is
`unassessed` by default, or `accepted`, `disputed`, or `rejected`.

```sh
docket claim "The API requires an idempotency key" --state accepted \
  --evidence https://example.test/api-docs \
  --revisit "When the API version changes"
```

Acceptance is a workflow status. It does not establish that the proposition is
true.

Use a **decision** for a commitment to a choice. Its state is `adopted` by
default or `revoked`. `--choice` is required. Repeat `--alternative` for other
recorded options; the choice is included automatically. Use `--decided-by` for
self-reported attribution when the recorder and decision owner differ.

```sh
docket decision "Which database should the service use?" \
  --choice "Postgres" \
  --alternative "SQLite" \
  --rationale "The service already runs Postgres in production" \
  --decided-by "platform team" \
  --cost "A later change requires a schema migration."
```

Adoption is a commitment status. It does not establish that the choice is
correct.

Use a **question** for an unanswered inquiry:

```sh
docket question "Which cache should we use?"
```

Questions always have recorded state `open`. A current accepted claim or
applicable adopted decision can give a question effective state `resolved` by
linking it with `--answers`. This derived state does not rewrite the question
line.

Type, recorded state, and currentness are separate. A later same-kind record
with `--supersedes` retires the earlier record from current views while keeping
its original line, state, and provenance. Retiring a replacement does not revive
its predecessor.

## When to record

Record a claim when a proposition will be used as a premise and may later need
review. Record a decision when the work reaches a commitment that later work
could contradict. Record a question when the inquiry remains unresolved.

Do not record active discussion, facts already clear from the code or document,
or a model's private reasoning. `author` identifies the recorder. Evidence,
`decided_by`, `revisit`, and `cost` are self-reported review metadata.

## Relationships

Use `--supports` for declared grounds. A CSV value is one complete AND set;
repeat the option for an OR alternative:

```sh
docket claim "The migration is safe" \
  --supports c1,c2 \
  --supports c3
```

This records `(c1 AND c2) OR c3`. It is not a verified implication and does not
propagate truth. References must name earlier claim or decision records.

Use `--depends-on` only on decisions for operational prerequisites. It is
separate from support alternatives. An adopted decision is applicable when its
claim prerequisites are accepted and current and its decision prerequisites are
adopted, current, and applicable. A derived decision can remain recorded as
`adopted` while reporting `blocked_by`; a blocked decision does not answer a
question.

Use `--answers` on a claim or decision to link it to an earlier question:

```sh
docket decision "Which cache should we use?" --choice "Redis" --answers q1
```

Only a current accepted claim or applicable adopted decision resolves the
question. Use `--supersedes` to replace a same-kind record. Docket rejects
unknown, later, or self references. It enforces relation target kinds. Duplicate
record IDs, cross-kind supersession, and supersession of an already retired
record are rejected.

The common options are `--scope` (repeatable), `--rationale`, `--supports`,
`--depends-on`, `--answers`, `--supersedes`, `--evidence` (repeatable),
`--revisit`, `--cost`, and `--pin`.

## Read current context and history

```sh
docket context
docket context --query "cache" --file src/cache.py --max-chars 4000
docket context --all --max-chars 12000
docket list
docket list --kind decision --state adopted --json
docket show d2 --json
docket graph --kind claim --state accepted
```

`context` renders two tiers. The full-text tier holds complete records for the
highest scoring records. The index tier names every other current record on one
line with its ID, kind, state, and clipped text. No current record is dropped
silently.

A record's score combines its file scope match, its query term rarity, its
position in the record sequence, whether it is pinned, and how many records
point at it. Each full-text record prints its score and components on a
`selection:` line. A scope match outranks a text match, because a scope states
where a record applies.

The budget target is 8000 characters. A record matching the task scope or query
renders in full even past the target, up to three times it. `--max-chars` sets a
hard ceiling instead, with a minimum of 512. `--all` puts every record in the
full-text tier and keeps the budget.

With no `--query` and no `--file`, `context` derives file scope from the working
tree's changed and untracked files. `--no-auto-scope` disables that and
`--auto-scope` forces it alongside an explicit query.

Weights, budget, index detail, and the auto-scope cap are tunable in
`.docket/config.toml`. See [the example](../../docs/config.example.toml). A
tuned briefing names its settings in the header.

Work with the briefing as follows:

1. Read the session briefing.
2. Identify the files the task will affect.
3. Re-run `docket context --file PATH` for those files. The working tree reports
   what already changed, and a task often touches files no diff mentions yet.
4. Run `docket show ID` for any index line the work depends on. An index line
   names a record; it does not carry the choice, scope, or rationale.
5. Record claims, decisions, and questions as the work produces them.

A delegated agent runs step 3 for its own scope and reports the revision it
used, so the delegating agent knows which briefing the work rests on.

`list` and `graph` accept `--kind` and `--state`. `show --json` exposes the
original record with derived fields such as `recorded_state`, effective `state`,
`retired_by`, `resolved_by`, `applicable`, and `blocked_by`. `graph` preserves
the full support sets as well as the renderer's deduplicated support union.

Evidence references are provenance supplied by the recorder. Docket does not
claim that evidence was freshly checked. Re-run `docket context` through the
harness's existing hook after compaction or resume.

## Ledger location

Run `docket where` to inspect the active ledger. `docket init` copies entries to
`.docket/ledger.jsonl` and makes that project ledger active. Set `DOCKET_HOME`
for another global directory, or use `CLAUDE_CONFIG_DIR` for an isolated Claude
profile. Commit `.docket/` when a team must share decisions.

Schema 1 ledgers require the explicit migration tool under `scripts/`; do not
guess record types from prose. See [the ledger reference](../../docs/ledger.md)
for the classification map, relation treatment, and non-overwriting migration
procedure.
