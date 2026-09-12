# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `docket context` prints a second tier that names every current record the
  full-text tier could not fit. Each unrendered record gets one index line, so
  an agent sees what exists and can retrieve it by ID. A budgeted briefing
  previously reported only a count of what it dropped.
- `docket context` derives file scope from git when you supply no `--query` and
  no `--file`: changed files plus untracked files, capped at the configured
  `auto_scope.limit` and 50 by default. Session
  hooks call `context` with no arguments, so an installed hook picks this up
  without a reinstall. `--no-auto-scope` disables it. `--auto-scope` forces it
  alongside an explicit query or file, unioning with any `--file` values.
- Query terms score by inverse document frequency over the current records. A
  term that appears in every record scores zero and drops out, so one common
  word no longer selects the whole ledger.
- `.docket/config.toml` sets the relevance weights, budget, index detail,
  expansion decay, and auto-scope cap that were constants in the source. Copy
  `docs/config.example.toml` to start. An unknown section or key is an error.
  Tuned settings change the order of a briefing, so the briefing header prints a
  fingerprint of them; a file that restates the defaults reports `default`.

### Changed

- **Docket requires Python 3.11 or later.** The previous floor was 3.10.
  Settings parsing uses the standard library `tomllib`, which arrived in 3.11.
  Upgrade your interpreter before upgrading Docket.
- `docket context` ranks records by an integer relevance score. Scope grades
  exact path above glob above directory prefix, and recency, relation degree,
  and pinning each contribute a weight. Scope outranks query text. The record ID
  breaks ties, so a briefing is byte-identical at one ledger revision. Ordering
  previously fell through to file position whenever two records both matched.
- The default character budget is a target. A record that matches the task scope
  or query renders in full past the target, bounded at three times it. An
  explicit `--max-chars` remains a hard ceiling.
- The briefing keeps naming records as the budget tightens. Over the ceiling it
  degrades in order: flat minimum index detail, then bare record names, then
  fewer names. The top-scoring record renders in full whenever any record fits.
  A ledger of 34 records is still named in full at the 512-character minimum.
  A budget below what the names alone cost drops the lowest-scoring ones, and
  the footer reports how many.
- Index lines carry between 40 and 140 characters of record text in proportion
  to the record's score, so a near miss says more than a distant record.
- Related-record expansion follows the score. A neighbour inherits half its
  parent's score per hop, and expansion stops when the inherited score falls
  under the floor. Traversal previously walked adjacency order and stopped at a
  flat cap of 64 records.
- The briefing header names the latest record ID and describes the selection
  that ran.

## [0.8.1] - 2026-09-12

### Changed

- `docket graph` styles the detail pane and makes the overview easier to read.
- The README drops detail that belongs in the reference documents, and
  `docs/definitions.md` states the formal definitions in their own section.

## [0.8.0] - 2026-09-12

This release changes the ledger format and replaces the recording commands. Read
the breaking-change notes before upgrading.

### Added

- Three typed record commands replace one generic one: `docket claim` records a
  proposition, `docket decision` records a commitment with its `--choice`, and
  `docket question` records an unresolved inquiry. IDs carry the type prefix and
  a shared sequence number: `c1`, `d2`, `q3`.
- Records carry typed relations: `supports` (alternative support sets),
  `depends_on` (decision prerequisites), `answers` (a claim or decision that
  resolves a question), and `supersedes`.
- Records carry a `scope` of path patterns or component names, a `rationale`,
  and a `pinned` flag.
- `docket context` selects records for a task: `--query` matches text, `--file`
  matches scope, `--max-chars` bounds the output at 8000 characters by default,
  and `--all` prints everything.
- `docket list --json` prints projected records. `docket list --kind` and
  `docket graph --kind` filter by record type.
- `docket graph` opens a native interactive viewer with a selectable tree,
  search, and a detail pane when it runs on a terminal. `--no-interactive`
  forces the static text renderer and `--interactive` forces the viewer. Piped
  output stays plain text. The viewer shows typed relations and marks a decision
  blocked by an unmet prerequisite.
- `scripts/migrate_ledger.py` converts a schema-1 ledger to schema 2 against a
  classification map you write. It validates every source relation and every
  mapped record before creating the destination, never overwrites the source or
  an existing destination, and records the original text and relation treatment
  in `legacy` metadata.
- The installer ships as a native binary for Linux, macOS, and Windows on amd64
  and arm64. `install.py` downloads the release binary for your platform,
  verifies its checksum, and runs it.

### Changed

- The ledger format is schema 2, written as append-only JSONL. Reads validate
  the whole file, so Docket reports an invalid line or relation instead of
  dropping it.
- States are per kind. A claim is `unassessed`, `accepted`, `disputed`, or
  `rejected`. A decision is `adopted` or `revoked`. A question is `open`.
  `--state` accepts these values.
- A question's recorded state stays `open`. A current accepted claim or
  applicable adopted decision linked through `answers` gives it the effective
  state `resolved` in derived views.
- `docket graph --style` has no default. The command picks the interactive
  viewer or the text renderer first, and `--style` applies to the text renderer.

### Removed

- `docket add`, `docket ruled-out`, and `docket open`. Use `docket claim`,
  `docket decision`, and `docket question`.
- The states `settled` and `ruled-out`.

### Breaking changes

- An existing schema-1 ledger fails to read, with an error naming the migration
  path. Migration is a separate, explicit operation: write a classification map
  that assigns a `kind`, `state`, and `text` to every source ID, run
  `scripts/migrate_ledger.py` with a new destination, check the record and
  relation counts, then switch the active ledger. Docket does not infer a record
  type from prose. See
  [the migration guide](docs/ledger.md#explicit-migration-from-schema-1).
- Scripts that call `docket add`, `docket ruled-out`, or `docket open` stop
  working. Move them to the typed commands.
- Scripts that pass `--state settled` or `--state ruled-out` stop working. Map
  them to the per-kind states above.

## [0.7.0] - 2026-09-12

### Added

- An installer. `python3 install.py` asks where the command goes, which
  harnesses to wire, and whether to touch your shell rc, then prints the whole
  plan and waits for one confirmation before writing anything. It detects Claude
  Code, Codex, Gemini CLI, Cursor, GitHub Copilot CLI, and OpenCode, and
  pre-selects the ones it finds. You can also select a harness it did not
  detect. `--yes`, `--no-tty`, `--dry-run`, `--uninstall`, and `--harness` skip
  the prompts. Uninstall keeps your ledgers.
- Running the installer again updates the checkout. It stages the new tree in a
  temporary directory and swaps it into place, keeping `.git`. The previous tree
  moves back if the swap fails. Updating previously ran `git pull --ff-only`,
  which failed outright when the install directory had local modifications.
- `docket graph` draws the support graph for a person. `--style forest` is the
  default; `--style rail` and `--style compact` are alternatives. `--state` and
  `--find` filter it. The graph includes retired entries, which `list` omits,
  so a support edge into a retired entry does not dangle.
- `docket context --for gemini|copilot|cursor` wraps the ledger in that
  harness's own hook JSON envelope, so a hook is one command.
- `docket --version` reads the new `VERSION` file, which both plugin manifests
  now track. The Codex manifest had drifted to 0.6.0 while the Claude one
  reached 0.6.3.
- `docket completion` prints a bash, zsh, or fish script that completes
  subcommands, flags, states, and entry IDs.
- `docket add` takes the answer positionally. `--answer` still works.
- `docket ruled-out` and `docket open` record an entry with the state fixed.
- `docket list --oneline` prints one truncated line per entry, so the mode pipes
  into grep.
- `docket show --json` prints the entry as JSON.
- A `justfile` with the build and test recipes.

### Changed

- `docket list` wraps to the terminal width and colours the ID and state. Five
  answers in this project's own ledger exceed 360 characters and previously
  printed on one line. The structure of the output is unchanged.
- Colour turns off when any agent environment variable is set, even on a
  terminal. Cursor, GitHub Copilot in VS Code, and Windsurf run agent commands
  over a pty, so a terminal check alone reports a person. `--plain` and
  `--pretty` force it either way.
- `docket show` prints a labelled, wrapped entry and resolves each cited ID to
  its question. **Anything parsing the old output must move to `--json`,** which
  reproduces the previous output byte for byte.
- Hooks no longer append `2>/dev/null || exit 0` to the command. That is sh
  syntax, and Claude Code runs hooks under PowerShell when Git Bash is absent.
  `context` already exits 0 and prints nothing for an empty ledger.
- Hook commands spell out the interpreter path on Windows, where `bin/docket`
  has no extension and no usable shebang.

## [0.6.3] - 2026-09-07

### Added

- `--supersedes` names the IDs an entry retires. The ledger is append-only, so
  an entry kept the state it was written with: a question recorded as open
  stayed open in `list --state open` and in the injected context even after a
  later entry answered it.
- `docket list --superseded` shows retired entries again, each marked with the
  ID that replaced it.

### Changed

- `docket list` and `docket context` drop a retired entry. `docket show` still
  reaches it directly, so the history stays readable.
- An unparseable `supersedes` is skipped with a warning to stderr, matching how
  a malformed `because` already degrades.

## [0.6.2] - 2026-09-07

### Changed

- The Lean experiment runs with `autoImplicit` off and binds its type variables
  explicitly. The CLI and the hook are unchanged from 0.6.1.

## [0.6.1] - 2026-09-07

### Added

- `docs/definitions.md` cites de Kleer on assumption-based truth maintenance and
  records the label-growth risk.
- A Lean experiment checks the outcome formalism, and a second one proves the
  parallel repair rather than restating it.

### Fixed

- `docket list` no longer crashes on a `because` field that mixes shapes, such
  as `["d1", ["d2", "d3"]]`. Only the first element was checked to decide
  between the flat and nested forms, and the mixed case reached a join with a
  list in it. Docket now validates the whole list against both known shapes and
  warns to stderr for anything else, naming the entry.

Versions before 0.6.1 carry no git tag. Their history is in the commit log.

[Unreleased]: https://github.com/NovusEdge/docket/compare/v0.8.1...HEAD
[0.8.1]: https://github.com/NovusEdge/docket/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/NovusEdge/docket/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/NovusEdge/docket/compare/v0.6.3...v0.7.0
[0.6.3]: https://github.com/NovusEdge/docket/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/NovusEdge/docket/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/NovusEdge/docket/releases/tag/v0.6.1
