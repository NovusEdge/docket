# Working with your agent

Docket exists because agents forget. A long session gets compacted, a new session
starts clean, and the choice you settled on Tuesday gets relitigated on Thursday.
The ledger is the memory that survives that.

## The two halves

Your agent tool needs two things from Docket.

A session hook runs `docket context` when a session starts and puts the output
in front of the model. That is how the agent learns what you already decided.

An instruction document tells the model when to record something. Docket ships
this as a skill, and the installer puts it where your tool looks for it.

The [installation page](installation.md#configure-an-agent-harness) has the exact
configuration for Claude Code, Codex CLI, Gemini CLI, Copilot CLI, Cursor, and
OpenCode. Every one of them reads the same ledger file, so you can use several
tools on one project without splitting your history.

## What the agent gets

The briefing arrives as text with a header, then the records that matter for the
current task. Each record says what kind it is and what role it plays. A decision
is a commitment the agent should honour. A claim is a premise the agent may
question. A question is work left open.

The briefing is honest about its own limits. It says when a record was retired by
a later one, it marks which records were cut for budget, and it states that
evidence was recorded rather than freshly checked. An agent that reads it knows
the difference between "we decided this" and "this is true".

## Telling the agent to record

You do not have to write the commands yourself. Say it in the session:

> Record that we are using asyncpg, because it is the fastest driver SQLAlchemy
> supports.

The agent runs the right `docket decision` command. Docket stamps the author,
the session, and the branch, so you can see later that the agent recorded it and
not you.

Ask the agent to record at the moment a choice gets made. A decision recorded
three days later has lost the reasoning that made it worth recording.

## Keeping the agent honest

Two habits pay off.

Ask for the open questions before you start a piece of work. `docket list --kind
question --state open` takes a second and often changes what you build.

Check the briefing yourself when an agent seems to be ignoring a decision. Run
`docket context --query "..."` with the task in the query. If the decision is not
in the output, the problem is usually a missing or overly narrow `--scope` on
that record.

## Where to go deeper

[Agent context goals](agent-context-goals.md) describes where this is heading and
which design questions are still open. [Decision chains](decision-chains.md) sets
out the problem this solves and the research behind the design.
