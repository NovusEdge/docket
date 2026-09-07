---
name: docket
description: Keep decisions available to later work. Use for settled choices, rejected options, open questions, reversals, and prior-decision checks.
---

# docket

Docket is an append-only decision ledger. It keeps decisions available after
conversation compaction.

Docket loads current decisions at session start. Read these decisions before you
start work.

## Decision states

**settled** - The decision applies to later work.

**ruled-out** - The work rejected this option.

**open** - The question does not have an answer.

## When to record a decision

Record a decision after the work reaches an answer. Do not record active
discussion.

Record a decision when later work could contradict it. Applicable decisions
include:

- A selected approach
- A rejected option
- A constraint from the user
- An assumption that supports later work

Do not record facts that the code or documentation already contains. Do not
record information that one file clearly shows.

## Run the command

Use the absolute command path from the session context. Do not assume that
`docket` is on `PATH`.

The examples use `docket` for readability. Replace it with the absolute path when
necessary.

## Record a decision

```sh
docket add "Which database?" --answer "Postgres with psycopg 3" \
  --cost "A later change requires a schema migration."

docket add "Use an ORM?" --state ruled-out \
  --answer "No. Use SQL for the full-text search queries."

docket add "Async or synchronous driver?" --state open \
  --answer "Select the driver after the concurrency requirement is known."
```

Use IDs from the current ledger. Use `--because` when earlier decisions support
the new decision. Separate joint requirements with commas:

```sh
docket add "Which async driver?" --answer "asyncpg" --because d3,d7
```

Repeat `--because` for alternative support sets:

```sh
docket add "Ship this quarter?" --answer "Yes." \
  --because d3,d7 \
  --because d12
```

Each `--because` occurrence records one complete support set. Repeat the option
to add an alternative set. The append-only ledger cannot add these links later.

Use `--cost` to record the effect of a reversal. Add this value when a reversal
has a high cost.

## Read decisions

```sh
docket list                    # Show all current entries.
docket list --state settled    # Show one state.
docket list --find postgres    # Search questions and answers.
docket list --superseded       # Include retired entries.
docket show d4                 # Show one entry as JSON.
```

## Replace a decision

Record the replacement and identify the retired entry with `--supersedes`:

```sh
docket add "Which database?" --answer "SQLite is sufficient." \
  --supersedes d3 \
  --cost "Review d9 and d11 because they depend on d3."
```

The retired entry keeps its recorded state. Normal lists and session context omit
the retired entry. `docket list --superseded` includes it.

Review entries that depend directly or indirectly on the retired ID. Docket does
not automatically retire dependent entries.

## Entry data

Each entry contains these fields:

- `question`
- `answer`
- `state`
- `because`
- `supersedes`
- `cost_if_wrong`
- `author`
- `session`
- `branch`.

Docket records these fields when it writes the entry. The append-only ledger
cannot change an earlier entry.

Set `DOCKET_AUTHOR` when the agent must use a specified author name. If author
detection fails, Docket records `"unknown"` and writes a warning to standard error.

## Ledger location

By default, Docket stores the ledger under `~/.claude/docket/`. It uses the Git
root to identify the project. Outside Git, it uses the current directory.

Run `docket where` to show the active ledger file.

Run `docket init` to copy existing entries to `.docket/ledger.jsonl`. The command
makes the project ledger active. A team can commit `.docket/` to share decisions.

## Limits

Docket records and recalls decisions. It does not block actions.

Docket records the selected answer. It does not claim that the recorded reason
matches the model's internal computation.
