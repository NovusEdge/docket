# Reading your ledger

You have four ways to get records back. `list` is for scanning, `show` is for
one record in full, `graph` is for how records connect, and `context` is what
your agent reads.

## Scan with list

```sh
docket list
```

```
d2    adopted   Which database should the billing service use?  <- c1
      Postgres
q3    resolved  Which async driver should the billing service use?
d4    adopted   Which async driver should the billing service use?
      asyncpg
c5    accepted  The service already runs Postgres in production
```

The `<- c1` marks a supporting record. Superseded records are hidden by default.

Narrow the list when it gets long:

```sh
docket list --kind question --state open
docket list --find postgres
docket list --oneline
docket list --superseded
```

`--json` prints the records as JSON, which is what you want when a script reads
them.

## Read one record with show

```sh
docket show d2
```

```
d2  decision  adopted  Which database should the billing service use?
  Choice: Postgres
  Rationale: We already run Postgres, so we add no new operational burden
  Because: c1 (The service already runs Postgres in production)
  Cost if wrong: A move to another engine means a migration and new runbooks
  Recorded state: adopted
  Author: claude-code  Session: session_01H...  Branch: main
```

`docket show d2 --json` gives you every field.

`--at` is the one people miss. It shows a record as history stood at some
earlier point:

```sh
docket show c1 --at d4
```

That answers "what did we think this said when we made that decision", which is
usually the question you actually have.

## See the shape with graph

```sh
docket graph
```

In a terminal this opens an interactive viewer. You move with the arrow keys or
`j` and `k`, expand a branch with space, switch panes with `tab`, search with
`/`, and quit with `q`. The [installation page](installation.md#browse-the-decision-graph)
lists every key.

Piped output stays static, so `docket graph | less -R` works. Force static
output with `--no-interactive`, and pick a layout with `--style forest`,
`--style rail`, or `--style compact`.

## What your agent sees

```sh
docket context
```

This is the briefing. Your agent tool runs it at the start of each session and
your agent reads the result. You can run it yourself any time you want to see
what the agent is working from.

The briefing does not dump the whole ledger. It scores every record against the
task and spends a character budget on the ones that matter. Records that match
the task appear in full. The rest appear as one line each, with instructions for
pulling the full record.

Aim the briefing at a task:

```sh
docket context --query "billing async driver"
docket context --file billing/db.py --file billing/worker.py
```

Without a query, Docket looks at your working tree and derives the scope from
the files you are changing. Turn that off with `--no-auto-scope`.

Two more flags help now and then. `--max-chars` changes the budget, with a floor
of 512. `--all` drops the relevance filter and keeps the budget.

`--since` reports what changed after a given record:

```sh
docket context --since d4
```

## Where to go deeper

The [ledger reference](ledger.md) explains how the briefing scores and selects
records. `docs/config.example.toml` in the repository lists every setting you can
tune, with the default and the reason for it.
