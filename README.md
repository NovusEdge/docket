# docket

Docket keeps decisions available during long agent tasks. It records settled
choices, rejected options, and open questions outside the conversation history.

When an agent session starts or resumes, Docket loads the current decisions.
The agent can continue after conversation compaction.

## Install for Claude Code

Docket requires Python 3.10 or later. It has no Python package dependencies.

Add the marketplace. Then, install the plugin:

```text
/plugin marketplace add NovusEdge/docket
/plugin install docket@NovusEdge
```

Start a new Claude Code session after the installation. The plugin loads the
current decisions and provides the Docket skill.

## Install the command

Clone the repository:

```sh
git clone https://github.com/NovusEdge/docket.git ~/Projects/docket
```

Add the command to your `PATH` if you want to use it in a shell:

```sh
mkdir -p ~/.local/bin
ln -s ~/Projects/docket/bin/docket ~/.local/bin/docket
```

Run this command to verify the installation:

```sh
docket --help
```

Confirm that the output starts with `usage: docket`.

## Record a decision

The default state is `settled`:

```sh
docket add "Which database?" \
  --answer "Postgres with psycopg 3" \
  --cost "A later change requires a schema migration."
```

Use `ruled-out` for a rejected option:

```sh
docket add "Use an ORM?" \
  --state ruled-out \
  --answer "No. Use SQL for the full-text search queries."
```

Use `open` when the work does not have an answer:

```sh
docket add "Which async driver?" \
  --state open \
  --answer "Select the driver after the concurrency requirement is known."
```

Use IDs that exist in your ledger. Use `--because` to identify supporting
decisions. Separate joint requirements with commas:

```sh
docket add "Use asyncpg?" \
  --answer "Yes." \
  --because d1,d3
```

Repeat `--because` to record alternative support sets:

```sh
docket add "Ship this quarter?" \
  --answer "Yes." \
  --because d1,d3 \
  --because d2
```

Each `--because` occurrence records one complete support set. Repeat the option
to add an alternative set.

## Read decisions

```sh
docket list
docket list --state settled
docket list --find postgres
docket show d3
docket context
```

`list` shows current entries. `show` prints one entry as JSON. `context` prints
the text that Docket gives to the agent.

## Replace a decision

Record a new decision and use `--supersedes` to retire the old entry:

```sh
docket add "Which database?" \
  --answer "SQLite is sufficient." \
  --supersedes d1 \
  --cost "Review the decisions that depend on d1."
```

Docket keeps the retired entry in the history. The normal list and agent context
show only current entries.

Use this command to include retired entries:

```sh
docket list --superseded
```

Docket does not automatically retire dependent decisions. Review decisions that
depend directly or indirectly on the retired ID through `--because`.

## Choose the ledger location

Inside a Git repository, Docket stores one global ledger per Git root under
`~/.claude/docket/`. Outside Git, it uses the current directory.

Use these commands to inspect or change the location:

```sh
docket where
docket init
```

`docket init` copies existing entries to `.docket/ledger.jsonl`. It also makes
that project ledger active. Commit `.docket/` when a team must share decisions.

Set `DOCKET_HOME` to select a different global directory. Docket also respects
`CLAUDE_CONFIG_DIR` for isolated Claude profiles.

See [installation options](docs/installation.md) for other agent harnesses.
