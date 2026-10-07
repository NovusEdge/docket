---
name: docket
description: Use when making a design choice, relying on a premise that may need review, leaving an open question, or before editing files that recorded decisions govern.
---

# docket

Docket is an append-only ledger of typed claims, decisions, and questions that survives conversation compaction. Read the current context before starting work. Run docket by the absolute command path on the `# command:` line of the briefing header; the examples say `docket`.

## Record types and states

A **claim** is a scoped proposition. Its recorded state is `unassessed` (default), `accepted`, `disputed`, or `rejected`. Accepted is a workflow status, not proof.

A **decision** is a commitment to a choice. Its state is `adopted` (default) or `revoked`. `--choice` is required; repeat `--alternative` for each option the choice beat; `--decided-by` is self-reported attribution when recorder and owner differ.

A **question** is an unanswered inquiry. Its recorded state is always `open`.

```sh
docket claim "The API requires an idempotency key" --state accepted --evidence https://example.test/api-docs
docket decision "The service uses Postgres." --choice "Postgres" --alternative "SQLite" \
  --rationale "The service already runs Postgres in production" --cost "A later change requires a schema migration."
docket question "Which cache should we use?"
```

Type, recorded state, and currentness are separate. A later same-kind record with `--supersedes` retires the earlier one from current views and keeps its line, state, and provenance. Retiring a replacement does not revive its predecessor.

## When to record

Record a claim when a proposition will be used as a premise and may later need review. Record a decision when the work reaches a commitment later work could contradict. Record a question when the inquiry stays unresolved.

Do not record active discussion, facts already clear from the code, or a model's private reasoning. Evidence, `decided_by`, `revisit`, and `cost` are self-reported.

## Relations

`--supports` names declared grounds. A comma list is one AND set; repeat the flag for an OR alternative. `--supports c1,c2 --supports c3` records `(c1 AND c2) OR c3`. It is not a verified implication and does not propagate truth.

`--depends-on` is for decisions only, and only for an operational prerequisite, never as a second `--supports`. Most decisions have none. A prerequisite is followed through restatements and revisions to the head of its chain; the head must be accepted (claim) or adopted and applicable (decision). A reversal, or a rejected or revoked head, blocks. A blocked decision stays recorded as `adopted`, reports `blocked_by`, and does not answer a question.

`--answers` links a claim or decision to an earlier question. Only a current accepted claim or applicable adopted decision makes the question's effective state `resolved`.

```sh
docket decision "Sessions live in Redis." --choice "Redis, one instance per environment" --answers q1
```

`--supersedes` replaces a same-kind record. References must name earlier records of the right kind; unknown, later, or self references, duplicate IDs, cross-kind supersession, and re-superseding a retired record are rejected.

Every id flag (`--depends-on`, `--answers`, `--supersedes`) may be repeated or comma-listed; `--supports` is the exception, where each occurrence is one OR set. A flag the kind cannot carry, such as `--depends-on` on a claim, is a usage error. Other options: `--scope`, `--evidence` (both repeatable), `--rationale`, `--revisit`, `--cost`, `--pin`. `--dry-run` on claim, decision, and question validates and prints the record without writing; `--json` prints the written record.

`docket record [FILE|-]` appends a JSONL batch, all or nothing: one invalid line writes nothing. `@N` names the Nth record of the batch. Use it when a session ends owing several linked records, so no record must be written before the ID it cites exists:

```sh
docket record - <<'EOF'
{"kind": "question", "text": "Which cache should we use?"}
{"kind": "decision", "text": "Sessions live in Redis.", "choice": "Redis", "answers": ["@1"]}
EOF
```

[Recording reference](../../docs/commands.md#recording) lists the fields a line may hold.

## Supersede, then review what follows

Pass `--supersede-reason`: `restate` for wording or link changes, `revise` for a change of substance, `reverse` when the old record was wrong. Records citing the retired one follow it to the new head; the reason decides whether they stay clean, owe review, or lose the ground. Then:

1. List the records that owe review: `docket list --where is:flagged`.
2. Take the frontier first: records whose `review_owed` items are not `because: flagged` or `blocked`.
3. Check the record against its changed grounds, then run `docket review ID`. It acknowledges only the record's own revised, unassessed, disputed, or circular grounds.
4. A flag inherited from a flagged or blocked ground clears when you review or fix that ground. `docket review` refuses such a record, so work down to the ground.

## Correct a record

Use `docket correct` when a record was written down wrong and its commitment still holds: a wrong scope, a question-shaped headline, a stale rationale.

    docket correct d12 --scope docket/env.py --reason "scope named the old path"

The record keeps its id, so records that support it keep their grounds. A correction cannot change `choice`, the state, or a relation; `--supersedes` instead when the commitment changed. A briefing tags a corrected record `corrected`; `docket show ID` lists corrections.

## What recording refuses, and what it only warns about

Refused outright:

- `--alternative` repeating the choice.
- `--rationale` restating the choice or the text.
- a claim's or decision's text ending in `?`; use `docket question` and link with `--answers`.
- a decision's text restating the choice; name what it commits to and leave option detail in `--choice`.

A field that looks filled while saying nothing is worse than an empty one, and a decision with no contender is a real decision.

Everything else prints a stderr hint and records anyway:

| Field | Leave empty when | Fill it when |
|---|---|---|
| `--scope` | the record governs the whole repository | any narrower path set applies; an unscoped record competes for room in every briefing |
| `--alternative` | nothing else was considered | another option was live and lost |
| `--rationale` | the choice line carries the reason | the reason is not visible in the choice |
| `--cost` | reversal costs nothing beyond the edit | reversal touches released artifacts, stored data, or others' work |

## Read context and history

```sh
docket context --query "cache" --file src/cache.py --max-chars 4000
docket context --since d40
docket list --kind decision --state adopted --json --fields id,state,text
docket list --where 'kind:decision is:pinned scope:docket/ledger.py'
docket show d2 --at d40
```

`context` renders two tiers: complete records for the best matches to the task, then one index line (ID, kind, state, clipped text) for each other current record, up to a cap. An index line names a record without its choice, scope, or rationale; it is not a coverage gap, because `docket show ID` fetches the record. A blocked decision prints a `blocked:` line per prerequisite chain, and the blocking record follows it in full.

Only an exact path scope or a query hit may exceed the character budget. `--max-chars` sets a hard ceiling; `--all` asks for every record in full, subject to the budget; `--explain` adds `selection:` lines showing why each record was picked. With no `--query` or `--file`, context scopes from the working tree's changed files, or the last commit when clean; `--no-auto-scope` disables that. [Ranking and budget](../../docs/ledger.md#bounded-context).

`context --since ID` reports what changed after that record. Pass the `latest: ID@DIGEST` pair from the header so a renumbered ID is caught. Nothing calls it for you: hooks fire only on startup, resume, clear, and compact. `show ID --at ID2` prints a record as history stood at ID2. [History reading](../../docs/ledger.md#reading-history-from-a-point).

Work the briefing in this order:

1. Read the session briefing.
2. Identify the files the task will affect.
3. Re-run `docket context --file PATH` for them; the tree reports what already changed, and a task often touches files no diff mentions yet.
4. Run `docket show ID` for any index line the work depends on.
5. Record claims, decisions, and questions as the work produces them.

A delegated agent runs step 3 for its own scope and reports the revision it used, so the delegator knows which briefing the work rests on.

`list` and `graph` accept `--kind`, `--state`, and `--where QUERY`, which combines words with `kind:`, `state:`, `scope:PATH`, `is:pinned`, `is:retired`, `author:`, `after:YYYY-MM-DD`, and `was:ID`, which finds a record by the ID it had before a migration; see [the query language](../../docs/commands.md#query-language). `scope:PATH` asks which records govern that file; `scope:DIR/` covers a directory.

`list --json` prints every field of every record, which is large: pass `--fields id,kind,state,text` for what you need. It and `show --json` drop the schema 1 `legacy` field unless you pass `--legacy`. See [the JSON shapes](../../docs/commands.md#json-shapes) for derived fields such as `recorded_state`, `applicable`, and `blocked_by`.

Evidence is recorder-supplied provenance; docket does not check it. Re-run `docket context` after compaction or resume.

## Elsewhere

- Graph export and `graph --web`, for a person to read: [reading your ledger](../../docs/reading.md#export-the-graph).
- Ledger location, `docket init`, `DOCKET_HOME`: [environment](../../docs/environment.md).
- A ledger older than this docket needs `docket migrate`; add `--rewrite FILE...` for tracked, clean files that cite ledger IDs, and never guess record types from prose. After a migration an old ID can name a different record: `docket list --where was:ID` finds the record that carried it. [Migrating](../../docs/ledger.md#migrating-to-schema-3).
- An unreadable ledger: `docket check`. A git conflict after two branches both recorded: `docket rebase OTHER --dry-run`, never a hand edit. Two branches that decided one question differently leave two adopted decisions; supersede one. [Sharing and maintenance](../../docs/maintenance.md).
