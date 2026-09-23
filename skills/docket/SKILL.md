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
default or `revoked`. `--choice` is required. Repeat `--alternative` for each
option the choice beat. Use `--decided-by` for self-reported attribution when
the recorder and decision owner differ.

```sh
docket decision "The service uses Postgres." \
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
docket question "Which cache should we use?"
docket decision "Sessions live in Redis." --choice "Redis, one instance per environment" --answers q1
```

Only a current accepted claim or applicable adopted decision resolves the
question. Use `--supersedes` to replace a same-kind record. Docket rejects
unknown, later, or self references. It enforces relation target kinds. Duplicate
record IDs, cross-kind supersession, and supersession of an already retired
record are rejected.

The common options are `--scope` (repeatable), `--rationale`, `--supports`,
`--depends-on`, `--answers`, `--supersedes`, `--evidence` (repeatable),
`--revisit`, `--cost`, and `--pin`.

## Correct a record

Use `docket correct` when a record was written down wrong and its commitment
still holds: a wrong scope, a question-shaped headline, a stale rationale.

    docket correct d12 --scope docket/env.py --reason "scope named the old path"

The record keeps its id, so records that support it keep their grounds. Use
`--supersedes` instead when the commitment itself changed: a correction
cannot change `choice`, the state, or a relation. A briefing tags a corrected
record `corrected`; `docket show ID` lists the corrections.

## What recording refuses, and what it only warns about

Four forms are refused outright:

- `--alternative` may not repeat the choice.
- `--rationale` may not restate the choice or the text.
- a claim's or decision's text may not end in `?`; record the question with
  `docket question` and link it with `--answers` instead.
- a decision's text may not restate the choice; name what the decision
  commits to and leave the option detail in `--choice`.

These are the shapes a recorder reaches for to fill a field it has nothing
for, and a field that looks filled while saying nothing is worse than an
empty one. Leave the option off instead. A decision that had no contender is
a real decision.

Everything else prints a hint on stderr and records anyway, because each of
these fields is legitimately empty for some records:

| Field | Leave it empty when | Fill it when |
|---|---|---|
| `--scope` | the record governs the whole repository | any narrower path set applies; an unscoped record competes for room in every briefing |
| `--alternative` | nothing else was under consideration | another option was live and lost |
| `--rationale` | the choice line already carries the reason | the reason is not visible in the choice |
| `--cost` | reversing the decision costs nothing beyond the edit | reversal touches released artifacts, stored data, or other people's work |

Scope leads the hints for a reason. Twenty records once shared one scope through
a migration, and a session editing documentation was briefed on Windows registry
semantics.

`--depends-on` is narrower than the rest. Use it only for an operational
prerequisite, never as a second `--supports`. Most decisions have none.

## Read current context and history

```sh
docket context
docket context --query "cache" --file src/cache.py --max-chars 4000
docket context --all --max-chars 12000
docket list
docket list --kind decision --state adopted --json
docket list --where 'kind:decision is:pinned scope:docket/ledger.py'
docket show d2 --json
docket show d2 --at d40
docket context --since d40
docket graph --kind claim --state accepted
```

`context` renders two tiers. The full-text tier holds complete records for the
highest scoring records. The index tier names the remaining current records on
one line each, with ID, kind, state, and clipped text. The index names at most
`index.max_lines` records, 40 by default, and closes with a count and
`docket list` for the rest. When the budget cannot hold every name, the footer
reports how many it left out.

A blocked decision prints one `blocked:` line for each chain of prerequisites,
which names every step and why the last one is unavailable. A record on such a
chain enters the full-text tier directly after the decision, under the label
`blocking prerequisite`.

The footer states coverage: either the task matches and their prerequisites all
reached the full-text tier, or how many stayed in the index. An index line is
not a coverage gap, because it names the record and gives the command that
fetches it.

A record's score combines its file scope match, its query term rarity, its
position in the record sequence, whether it is pinned, and how many records
point at it. Each full-text record prints its score and components on a
`selection:` line. An exact path scope outranks an explicit `--query`, and a
query outranks a glob or directory scope: a query states the task, and a scope
derived from the working tree guesses at it.

The budget target is 8000 characters. A record matching the task scope or query
renders in full even past the target, up to three times it. `--max-chars` sets a
hard ceiling instead, with a minimum of 512. `--all` asks for every record in
the full-text tier, subject to the budget; a record that does not fit falls to
an index line.

With no `--query` and no `--file`, `context` derives file scope from the working
tree's changed and untracked files. `--no-auto-scope` disables that and
`--auto-scope` forces it alongside an explicit query. A clean tree scopes from
the paths the last commit touched. A repository with no commits stays unscoped.

`docket context --since RECORD_ID` reports what changed after that record: the
records added since, and the records that lost availability since. The header
prints `latest: ID@DIGEST`, and `--since` accepts that pair. `docket rebase`
renumbers a tail, so the digest catches a baseline ID that now names a different
record. An unknown or stale baseline prints a note on stderr, then a full
briefing. Nothing calls `--since` for you: the session hooks fire on startup,
resume, clear, and compact only.

`docket show ID --at RECORD_ID` prints the record as history stood at that
record. A supersession or an answer recorded later does not appear.

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

`list` and `graph` accept `--kind`, `--state`, and `--where QUERY`. A query
combines plain words with `kind:`, `state:`, `scope:PATH`, `is:pinned`,
`is:retired`, `author:`, and `after:YYYY-MM-DD` terms; see
[the query language](../../docs/commands.md#query-language). `scope:PATH` asks
which records govern that file, and `scope:DIR/` covers a directory.

`show --json` exposes the
original record with derived fields such as `recorded_state`, effective `state`,
`retired_by`, `resolved_by`, `applicable`, and `blocked_by`. `graph` preserves
the full support sets as well as the renderer's deduplicated support union.

`graph --format` exports the relation graph instead of drawing it.

| Format | Output | For |
|---|---|---|
| `mermaid` | stdout | pasting into a fenced block a reader already renders |
| `dot` | stdout | `dot -Tsvg`, and a layout that holds up past a hundred nodes |
| `csv` | `nodes.csv` and `edges.csv` in `--out DIR` | Gephi, or anything measuring the graph rather than drawing it |

`--kind`, `--state`, `--find`, `--where`, `--superseded` and `--detail` narrow all three.
Narrow before exporting: the whole ledger is a hairball in any of them.

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

## Repair a shared ledger

```sh
docket check
docket rebase ../other-branch/.docket/ledger.jsonl --dry-run
docket rebase ../other-branch/.docket/ledger.jsonl
```

Run `check` when any command reports an unreadable ledger. It lists every fault
with its line number, where a read stops at the first one.

Run `rebase` when two branches both recorded and the ledger conflicts in git.
It appends the other branch's records past the shared prefix under fresh IDs and
rewrites the references inside them. Never resolve the conflict by editing the
file: a kept record can end up pointing at a same-numbered record from the other
branch, which validates and is wrong. `--dry-run` prints the ID map first.

Two branches that decided one question differently produce two adopted decisions.
Supersede one of them; a rebase does not choose.
