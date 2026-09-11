# docket

Docket keeps decisions available during long agent tasks. It records settled
choices, rejected options, and open questions outside the conversation history.

When an agent session starts or resumes, Docket loads the current decisions.
The agent can continue after conversation compaction.

## Install

Docket requires Python 3.10 or later. It has no Python package dependencies.

```sh
curl -fsSLO https://raw.githubusercontent.com/NovusEdge/docket/main/install.py
python3 install.py
```

The installer adds the `docket` command to your `PATH`. It also configures each
agent harness that it finds on your machine: Claude Code, Codex, Gemini CLI,
Cursor, GitHub Copilot CLI, and OpenCode.

Run `python3 install.py --dry-run` first to see every file that the installer
writes. Run `python3 install.py --uninstall` to remove them. The uninstall keeps
your decision ledgers.

Run the installer again to update. It pulls the current version and rewrites the
configuration.

Start a new agent session after the installation. Then run this command to
verify:

```sh
docket --version
```

For one harness at a time, a project-local installation, or manual
configuration, see [installation options](docs/installation.md).

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

The answer can come positionally or via `--answer`, not both:

```sh
docket add "Which database?" "Postgres with psycopg 3"
```

`docket ruled-out` and `docket open` are shorthand for `add --state ruled-out`
and `add --state open`. They accept `--because`, `--supersedes`, and `--cost`
like `add` does:

```sh
docket ruled-out "Use an ORM?" "No. Use SQL for the full-text search queries."
docket open "Which async driver?" "Select the driver after the concurrency requirement is known."
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
docket list --oneline
docket show d3
docket show d3 --json
docket context
```

`list` shows current entries, wrapped and coloured to the terminal; `--oneline`
prints one line per entry with no answer. `--plain` and `--pretty` force the
colour gate off or on. `show` prints one entry, human-readable, resolving its
`--because` ids to the question text they cite; `--json` prints the entry as
stored. `context` prints the text that Docket gives to the agent.

`docket completion bash|zsh|fish` prints a completion script for that shell.

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
