# Working with your agent

You can ask your agent to record a decision, look up an earlier choice, or list
the questions that still need answers. Docket keeps those records available
across sessions.

## Connect your agent

Use the [setup prompt](installation.md#let-your-agent-handle-setup) to let your
agent install Docket and configure its integration. If you prefer manual setup,
the [installation guide](installation.md#configure-an-agent-harness) has a route
for Claude Code, Codex, Gemini CLI, GitHub Copilot CLI, Cursor, and OpenCode.

After setup, start a new session in your project. Ask:

> Read the Docket context for this project and tell me which questions are still
> open.

The integration loads a briefing and gives the agent instructions for using
Docket. If you prefer to configure it yourself, use the
[agent setup reference](integrations.md).

Different agent tools can use the same project ledger when they run in the same
checkout. To share records with another checkout or computer, commit and sync
`.docket/` through Git.

## Ask for a record when a choice is made

You can say:

> Record that billing will use Postgres because we already operate it. Scope
> the decision to billing/**.

Give the agent the choice and the reason you want preserved. It can then record
them with the Docket command.

For an unresolved issue:

> Leave an open question about which database driver billing should use.

For a change of direction:

> Replace the earlier driver decision with asyncpg and record why we changed it.
> Keep it linked to the question it answers.

The agent should use `--supersedes` to preserve the earlier record. You can
inspect what it recorded with `docket list` and `docket show ID`.

## Start work with the relevant context

Before a new task, ask:

> Read the Docket context for billing and check the open questions before making
> changes.

For a more specific briefing, you or your agent can run:

```sh
docket context --query "billing database" --file billing/db.py
```

The briefing distinguishes a recorded choice from a claim that may need review.
An accepted claim still needs fresh checking when its evidence could have
changed.

After compaction or a long break, ask the agent to read the context again. The
integration's refresh behavior depends on the agent tool, and a briefing already
loaded into a conversation does not update itself.

## When a decision is missing

First, check that the record exists in the active ledger:

```sh
docket where
docket list --find billing
```

Then request a focused briefing:

```sh
docket context --query "billing" --file billing/db.py
```

A record may appear in the index rather than in full. Ask the agent to retrieve
it by ID. If it does not appear at all, check the ledger location and whether
the record's wording or scope matches the task.

To change a scope, record a replacement with `--supersedes`. To inspect a record
immediately, use `docket show ID --json` without changing the ledger.

If the command works in your terminal but the agent receives no briefing, start
a new session and check its [integration setup](integrations.md). If the command
itself fails, run `docket check` and see [Maintenance](maintenance.md).

## Know who recorded a choice

Docket records an author and includes session and branch information when
available. These describe who recorded the entry; they do not establish who
approved the choice.

Use `--decided-by` when the decision owner is someone else. This is recorded
attribution, not an authenticated identity.

For the hook formats and instruction files, see
[Agent setup reference](integrations.md). For how a briefing is selected, see
[Bounded context](ledger.md#bounded-context).
