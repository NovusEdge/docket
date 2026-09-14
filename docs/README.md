# Docket

Docket tracks the decisions a project makes across sessions, and checks what
breaks when one of them changes.

A record is one of three kinds. A **claim** is a statement the work depends on.
A **decision** is a choice, with the reason for it. A **question** is something
still open.

Records are only ever added. Nothing is changed or deleted. A later record can
replace an earlier one, and the earlier one stays in the file, so you can read
back how a choice changed.

Records link to each other. A record lists the ones it rests on, and a decision
lists the ones it depends on. Mark a claim rejected, and every decision that
depends on it is flagged as blocked.

A coding agent reads the current records before it works, so what you already
settled is there from the start.

The records are one file in your project, shared through Git.

## Start here

The [quickstart](quickstart.md) walks you through your first decision and shows
how to read it back. You can use Docket from a terminal or ask your agent to
record things for you.

| I want to… | Read |
|---|---|
| Ask my agent to set up Docket | [Copy the setup prompt](installation.md#let-your-agent-handle-setup) |
| Install Docket myself | [Choose an install route](installation.md#configure-an-agent-harness) |
| Try it in a project | [Your first decision](quickstart.md) |
| Save a choice or leave a question for later | [Recording decisions](recording.md) |
| Find an earlier decision | [Reading your ledger](reading.md) |
| Use Docket in an agent session | [Working with your agent](agents.md) |
| Share a ledger with my team | [Sharing and maintenance](maintenance.md) |

## What goes in a ledger?

The file holding the records is called a **ledger**. The rest of this
documentation uses that name. It holds three kinds of record:

| Record | What it keeps | Example |
|---|---|---|
| **Claim** | A statement you want to assess or rely on | “The service already runs Postgres.” |
| **Decision** | A choice and the reason for it | “Use Postgres for billing because we already operate it.” |
| **Question** | Something you still need to find out | “Which database driver should we use?” |

You can connect a decision to the claims behind it or to a question it answers.
When your choice changes, add a replacement. The earlier record remains
available so you can follow how the decision changed.

## Pick up where you left off

Configured agent integrations load a **briefing** from the ledger. It gives the
agent relevant records and instructions for finding more.

You can also ask for context about a particular task:

```sh
docket context --query "billing database"
```

Docket supplies the recorded context. You and your agent still need to check
whether the evidence is current and whether a choice fits the work in front of
you.

## When you want more detail

Use the [command reference](commands.md) to look up a flag. The
[ledger reference](ledger.md) explains states, relationships, and how Docket
chooses records for a briefing.

The **Design and research** section explores the ideas behind Docket and
proposals for future work. You can use the everyday guides without reading it.

[Source code](https://github.com/NovusEdge/docket) ·
[Releases](https://github.com/NovusEdge/docket/releases)
