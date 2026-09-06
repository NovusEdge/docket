---
name: docket
description: Use when a decision gets made during a long piece of work that later steps must not silently contradict, when the user asks what was already decided, when reopening a settled decision, or when they say "docket", "record this", or "what did we settle". Records decisions to an append-only ledger that loads at session start.
---

# docket

An append-only ledger of decisions. It exists because compaction removes the
prose that held a decision, and later work then contradicts it without noticing.

The ledger loads automatically at session start. Decisions already recorded
appear in context before you do anything.

## The three states

**settled** — decided, and binding on everything after it.

**ruled-out** — eliminated, with the reason. Stops the same ground being
re-covered.

**open** — unresolved, and carried forward as such.

## When to record

Record after a decision is actually made, not while it is being discussed.

A decision belongs in the ledger when a later step could contradict it without
anyone noticing. That covers a chosen approach, a rejected alternative, a
constraint the user stated, and an assumption the work now rests on.

It does not cover facts, which the code or the docs already hold. It does not
cover things obvious from one file. Do not record every exchange.

## Running the command

The session context printed by docket at startup names the absolute path to the
command. Use that path. Do not assume `docket` is on PATH, because putting it
there is an optional step the user may not have taken.

The examples below write `docket` for readability. Substitute the path from the
session context.

## Recording

```sh
docket add "Which database?" --answer "Postgres via psycopg 3" \
  --cost "migration rewrite if reversed after schema lands"

docket add "Use an ORM?" --state ruled-out \
  --answer "No. Raw SQL for the FTS queries, which is the point of the exercise."

docket add "Async or sync engine for the CLI preset?" --state open \
  --answer "Undecided. Sync unless a caller needs concurrency."
```

Use `--because` when a decision only holds because an earlier one does. Pass the
ids it depends on.

```sh
docket add "Which async driver?" --answer "asyncpg" --because d3,d7
```

A decision can rest on more than one independent line of support. Repeat
`--because` for each alternative; the claim survives while any one of them
still holds.

```sh
docket add "Ship this quarter?" --answer "Yes" --because d3,d7 --because d12
```

Justifications matter later. The ledger is append-only, so an entry written
without them can never gain them. When a decision rests on another, say so as
you record it.

`--cost` states what breaks if the decision is reversed later. Write it for
anything expensive. Skip it for anything cheap.

## Reading

```sh
docket list                    # everything
docket list --state settled    # one state
docket list --find postgres    # match question or answer text
docket show d4                 # one entry as JSON
```

## Reopening a decision

The ledger never edits or deletes. To reverse a decision, record the reversal and
name the entry it replaces.

```sh
docket add "Which database? (reopens d3)" --answer "SQLite. Postgres was overkill." \
  --cost "d9 and d11 assumed Postgres and need rechecking"
```

Then check every entry whose `because` names the reopened id, and say plainly
which ones no longer hold. Retraction is manual in this version.

## What each entry carries

Alongside the question, answer, state, `because`, and `cost_if_wrong`, every
entry records who wrote it, which session, and which branch. These are captured
at write time because the log is append-only and cannot gain them later.

Set `DOCKET_AUTHOR` when an agent should identify itself by name. When no
author can be detected, the entry records `"unknown"` rather than a blank
field, and docket prints a warning to stderr naming `DOCKET_AUTHOR`.

## Where the ledger lives

By default the ledger sits under `~/.claude/docket/`, keyed by the project's
path. A new project needs no setup and no gitignore entry.

Run `docket where` to print which file is in use.

Run `docket init` to move the ledger into the repository as `.docket/`, which is
how a team commits and shares decisions. Any existing entries move with it.

## What this does not do

It does not block actions. It records and recalls, and nothing more.

It does not record why a decision was made. A stated chain of reasoning often
fails to reflect the computation behind an answer, so treat the ledger as a
record of what was committed to, checkable against later behavior.
