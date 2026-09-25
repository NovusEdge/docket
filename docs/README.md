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

Read [Why Docket?](why.md) for the problems it addresses and when a simpler set of notes may be enough.

## Start here

<table data-view="cards">
<thead><tr>
<th></th>
<th></th>
<th data-hidden data-card-target data-type="content-ref"></th>
</tr></thead>
<tbody>
<tr>
<td><strong>Set up Docket</strong></td>
<td>Paste a prompt and let your agent do it, or install it yourself.</td>
<td><a href="installation.md">installation.md</a></td>
</tr>
<tr>
<td><strong>Your first decision</strong></td>
<td>Record a choice in a real project and read it back.</td>
<td><a href="quickstart.md">quickstart.md</a></td>
</tr>
<tr>
<td><strong>Command reference</strong></td>
<td>Look up a command or a flag.</td>
<td><a href="commands.md">commands.md</a></td>
</tr>
</tbody>
</table>

You can use Docket from a terminal or ask your agent to record things for you.
Once it is set up:

| I want to… | Read |
|---|---|
| Save a choice or leave a question for later | [Recording decisions](recording.md) |
| Find an earlier decision | [Reading your ledger](reading.md) |
| Use Docket in an agent session | [Working with your agent](agents.md) |
| Start from years of existing design notes | [Constructing on existing projects](construct.md) |
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

The [ledger reference](ledger.md) explains states, relationships, and how Docket
chooses records for a briefing.

The **Design and research** section explores the ideas behind Docket and
proposals for future work. You can use the everyday guides without reading it.

[Source code](https://github.com/NovusEdge/docket) ·
[Releases](https://github.com/NovusEdge/docket/releases)
