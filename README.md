# docket

Docket keeps decisions available during long agent tasks. It stores typed,
append-only records for propositions, commitments, and unanswered questions so
an agent can recover the relevant context after conversation compaction.

Version 0.8.0 changes the ledger format to schema 2. The old `add`, `open`,
`ruled-out`, `--answer`, and `--because` interface is removed. A schema 1
ledger must be migrated explicitly. See [the ledger reference](docs/ledger.md)
for the record format and migration boundary.

## Install

Docket requires Python 3.10 or later. It has no Python package dependencies.

```sh
curl -fsSLO https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py
python3 install.py
```

`curl -O` saves the file as `install.py` in the current directory. From a
checkout, run `python3 installer/install.py` instead.

In a terminal, the installer walks you through the command location, which
harnesses to configure, and the PATH change, then shows the full plan before
writing anything. It detects Claude Code, Codex, Gemini CLI, Cursor, GitHub
Copilot CLI, and OpenCode, and lets you select an undetected harness.

The launcher downloads a native installer for Linux, macOS, or Windows and
checks its SHA-256 checksum before running it. The installer also prepares the
native graph viewer for Linux, macOS, or Windows on amd64 and arm64. A
published install verifies the viewer against `GRAPH-SHA256SUMS`; an install
from a source checkout builds `graph/docket-graph` locally when Go is
available. From a checkout, the launcher builds the installer locally; this
requires Go 1.26 or later. If no matching viewer asset is published and Go is
unavailable, the installer reports the missing release.

Add `--yes` for defaults-only behavior with no prompts, the same mode CI uses.
Add `--dry-run` to see every file the installer would write. Add `--update` to
refresh the existing Docket checkout and native graph viewer without changing
harness configuration or PATH. Add `--uninstall` to remove the integrations;
uninstall keeps the ledgers.

Start a new agent session after installation. Then verify the command:

```sh
docket --version
```

For one harness at a time, a project-local installation, or manual
configuration, see [installation options](docs/installation.md).

## Record typed entries

A claim is a proposition. Its state is `unassessed`, `accepted`, `disputed`, or
`rejected`; `accepted` records a workflow judgment and does not establish that
the proposition is true.

```sh
docket claim "The API requires an idempotency key"
docket claim "The API requires an idempotency key" --state accepted \
  --evidence https://example.test/api-docs \
  --revisit "When the API version changes"
```

A decision is a commitment to a choice. Its state is `adopted` or `revoked`.
The selected choice is required and is included in `--alternative` values
automatically. Use `--decided-by` when the commitment is attributed to a
person or agent other than the recorder.

```sh
docket decision "Which database should the service use?" \
  --choice "Postgres" \
  --alternative "SQLite" \
  --rationale "The service already runs Postgres in production" \
  --decided-by "platform team" \
  --cost "A later change requires a schema migration."
```

A question records an unresolved inquiry. Its recorded state is always `open`.
A current applicable answer can give it effective state `resolved` in a derived
view. The original question line remains unchanged.

```sh
docket question "Which async driver should the service use?"
```

All three commands allocate the next global sequence number. Claim IDs start
with `c`, decisions with `d`, and questions with `q`. IDs therefore identify
both the record and its type, for example `c1`, `d2`, and `q3`.

The shared record options are `--scope` (repeatable path or component scope),
`--rationale`, `--supports`, `--depends-on`, `--answers`, `--supersedes`,
`--evidence`, `--revisit`, `--cost`, and `--pin`. Evidence can be a plain
reference or a JSON object with a required `ref` and optional `checked_at` and
`commit` fields. Relations must name earlier records.

Use `--supports` for declared grounds. Each CSV value is an AND set; repeating
the option records an OR alternative:

```sh
docket claim "The migration is safe" \
  --supports c1,c2 \
  --supports c3
```

This means `(c1 AND c2) OR c3`. It records a support formula. It does not prove
the claim, verify the evidence, or enumerate transitive support sets.

Use `--depends-on` only for a decision's operational prerequisites. A dependency
means that the decision needs those records to be usable; it is separate from
the `--supports` grounds and its AND/OR alternatives.

Use `--answers` on a current accepted claim or applicable adopted decision to
resolve an earlier question in the derived view. A blocked decision does not
answer a question:

```sh
docket question "Which cache should we use?"
docket decision "Which cache should we use?" --choice "Redis" --answers q1
```

The answer link does not rewrite the question's original state. A superseding
answer stops resolving it. `--supersedes` retires records of the same type while
preserving their original lines and recorded states. A decision can remain
`adopted` while its derived view reports `blocked_by` unavailable prerequisites.

## Read the ledger

```sh
docket list
docket list --kind claim --state accepted
docket list --json
docket show c1
docket show d2 --json
docket graph --kind decision --state adopted
docket context --query "cache" --file src/cache.py --max-chars 4000
```

`list` and `graph` accept `--kind` and `--state` filters. `show --json` returns
the original record together with clearly named derived fields when needed,
including recorded and effective state, retirement, and question resolution.
Use `docket list --json` when an agent needs machine-readable entries.

`context` builds a bounded startup or task briefing from the projected ledger.
Use `--query` for a task, repeat `--file` for relevant paths, `--max-chars` for
the character budget, and `--all` to remove relevance filtering. The budget is
characters, not tokens. Docket keeps complete record blocks and support formulas
within the budget, reports omitted records, and prints a retrieval command.
It does not claim that supplied evidence was freshly checked.

`docket completion bash|zsh|fish` prints a completion script for that shell.

## Choose the ledger location

Inside a Git repository, Docket stores one global ledger per Git root under
`~/.claude/docket/`. Outside Git, it uses the current directory.

```sh
docket where
docket init
```

`docket init` copies existing entries to `.docket/ledger.jsonl` and makes that
project ledger active. Commit `.docket/` when a team must share decisions.

Set `DOCKET_HOME` to select a different global directory. Docket also respects
`CLAUDE_CONFIG_DIR` for isolated Claude profiles. See [installation options](docs/installation.md)
for harness hooks and [decision chains](docs/decision-chains.md) for the
formal motivation.
