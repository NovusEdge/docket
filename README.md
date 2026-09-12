# docket

Docket keeps decisions available during long agent tasks. It records settled
choices, rejected options, and open questions outside the conversation history.

When an agent session starts or resumes, Docket loads the current decisions.
The agent can continue after conversation compaction.

## Install

Docket requires Python 3.10 or later. It has no Python package dependencies.

```sh
curl -fsSLO https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py
python3 install.py
```

`curl -O` saves the file as `install.py` in the current directory. From a
checkout, run `python3 installer/install.py` instead.

In a terminal, the installer walks you through the command location, which
harnesses to configure, and the PATH change, and shows the full plan before
writing anything. It detects Claude Code, Codex, Gemini CLI, Cursor, GitHub
Copilot CLI, and OpenCode, and pre-selects the ones it finds; you can select an
undetected one too, if you're about to install it.

The launcher downloads a native installer for Linux, macOS, or Windows and
checks its SHA-256 checksum before running it. The installer also prepares the
native graph viewer for Linux, macOS, or Windows on amd64 and arm64. A
published install verifies the viewer against `GRAPH-SHA256SUMS`; an install
from a source checkout builds `graph/docket-graph` locally when Go is
available. From a checkout, the launcher builds the installer locally; this
requires Go 1.26 or later.
If the checked-out version has no published viewer assets and Go is unavailable,
the installer reports the missing release rather than selecting another
version.

Add `--yes` for the defaults-only behaviour with no prompts, the same as CI
uses. Add `--dry-run` to see every file the installer would write. Add
`--update` to refresh the existing Docket checkout and native graph viewer
without changing harness configuration or PATH. It requires the installed
`docket` command and accepts `--dry-run`. Add `--uninstall` to remove the
integrations. The uninstall keeps your decision ledgers.

Run the installer again to update. It pulls the current version and rewrites the
configuration.

`docket graph` opens the native interactive viewer when `graph/docket-graph` is
present and the command has a terminal on both input and output. Installing a
Claude or Codex plugin from this repository supplies skills and hooks only; it
does not download a compiled viewer. For a source checkout, run
`just graph-build` when Go is available. If the viewer is absent, automatic
mode prints a concise installation hint and uses the compact text renderer;
graph invocation never downloads or builds anything. Use `--interactive` to
require the viewer or `--plain` for text output.

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
