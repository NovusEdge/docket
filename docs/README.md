# Docket

Docket is a decision ledger for coding agents. You record what you decided and
why. Docket hands it back to your agent when it becomes relevant again.

Agents forget. A long session gets compacted, a new session starts clean, and a
choice you settled on Tuesday gets argued again on Thursday. Docket is the memory
that survives that.

```sh
docket decision "Which database should the billing service use?" \
  --choice "Postgres" \
  --rationale "We already run Postgres, so we add no new operational burden" \
  --scope "billing/**"
```

Records live in an append-only file. Nothing is ever edited, so when you change
your mind, the old reasoning stays readable next to the new one.

## Start here

New to Docket? The [quickstart](quickstart.md) gets you from nothing to a working
ledger in about five minutes.

After that, [Recording](recording.md) covers the day to day habit, and
[Reading](reading.md) shows the four ways to get your records back.

## Guides

| Page | What it covers |
|---|---|
| [Quickstart](quickstart.md) | Install, create a ledger, record your first decision |
| [Recording](recording.md) | Claims, decisions, questions, and how to link them |
| [Reading](reading.md) | `list`, `show`, `graph`, and the briefing your agent reads |
| [Working with your agent](agents.md) | How Docket plugs into your agent and what it sees |
| [Installation](installation.md) | Every install path, agent setup, updates, uninstall |
| [Maintenance](maintenance.md) | Merge conflicts, broken ledgers, tuning, completion |
| [Command reference](commands.md) | Every command and flag |

## Going deeper

These pages are for readers who want the detail behind the design. You do not
need them to use Docket.

| Page | What it covers |
|---|---|
| [Ledger reference](ledger.md) | Record types, states, relations, file format, scoring |
| [Definitions](definitions.md) | The formal vocabulary the design documents use |
| [Decision chains](decision-chains.md) | The problem, the research, and the resulting design |
| [Outcome formalism](outcome-formalism.md) | Outcomes, chains, and claims as a formalism |
| [Agent context goals](agent-context-goals.md) | Where agent context is heading, and what is still open |
| [North star](north-star.md) | The target system and its build order |
