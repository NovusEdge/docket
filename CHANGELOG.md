# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `just release` now rolls the changelog, and refuses to release while
  `## [Unreleased]` is empty. 0.13.0 shipped with its entry still under that
  heading and nothing reported it. `scripts/roll_changelog.py` moves the
  section under a dated version heading and moves the compare links with it.
  (#20)

### Documentation

- `docs/recording.md` and `docs/ledger.md` now state the two tiers 0.14.0
  introduced: a repeated `--alternative` or a restated `--rationale` is
  refused, four reasoning fields hint and record anyway, and both checks run
  at write time so an older ledger still reads. (#18)
- `docs/north-star.md`, `docs/agent-context-goals.md` and `docs/definitions.md`
  now separate the exercised parts of the schema from the provisional ones,
  with the counts from this ledger. No decision has ever derived as blocked,
  one record carries more than one support set, and nine declare a
  prerequisite. (#19)
- `docs/installation.md` covers running setup again on a machine that already
  has Docket, which is how a second harness or a construct provider gets
  added. It names what carries forward, what must be repeated, and what
  `--dry-run` shows. (#21)

## [0.17.0] - 2026-09-19

### Added

- `docket graph --format mermaid` and `--format dot` print the relation graph
  as text. Mermaid renders in GitHub, GitLab and GitBook with nothing
  installed; DOT lays out a large graph better and gives real SVG through
  `dot -Tsvg`, and the reader needs graphviz for it. The `--kind`, `--state`
  and `--find` filters narrow either one, `--superseded` adds the retired
  records and their retire edges, `--detail N` sets the text per node, and
  `--direction` sets the layout. Each relation reads apart without a legend,
  the record kind picks the node shape, and a record carrying more than one
  support set gets a join node per set, so the diagram never draws it as
  needing every premise at once. DOT wraps a label over several lines, because
  a hexagon or an ellipse grows sideways to hold its text and one long line
  turns a question into a lozenge wider than the rest of the graph.
- `docket feature amend --clear FIELD` empties a declared list: `include`,
  `exclude` or `intends`. Each of those flags replaces the whole list, so a
  wrongly added override could be changed but never removed. `paths` is not
  clearable, because `start` requires at least one.
- `docket check` now reads `.docket/archive/` as well. The archive holds the
  only copy of the events `gc` moved, and a fault in it surfaced from
  `docket feature show` instead.

### Fixed

- `docket check` built its known-ID set with the strict reader, so one bad
  ledger line aborted the command that exists to report every bad line, and
  the `include`/`exclude` validation never ran. It now reads the IDs it
  already collected.
- `docket feature brief` matched declared paths against the tracked tree with
  its own case-sensitive matcher, while `done` classifies with a matcher that
  casefolds. A declared path holding an uppercase letter put files in the
  brief that the intentional set then rejected. Both now call one matcher.
- Bash completion offered nothing for the word `feature` itself, because the
  feature branch ran while the cursor was still on that word. It also offered
  no flags inside the group.
- A session start read and projected the ledger twice, once for the records
  and once for the feature brief. It now reads it once.
- `.docket/` counted as realized work. A commit that recorded a decision
  landed in a feature's unintentional set, and the claim prompt then asked
  about claims scoped to `ledger.jsonl`. The change set excludes it, matching
  what the dirty-tree check already did.
- The feature brief's budget footer told the reader to run
  `docket feature show`, which prints a feature and never its attached
  records. It now names `--detail` and the declared paths.

### Changed

- Every module in `docket/` and `docket/cli/` that carried two jobs is split
  so each file holds one, and none of the four named in review exceeds 300
  lines. `docket/context.py` becomes `context_model`, `context_select`,
  `context_render`, `context_budget`, `context_degrade` and `context_delta`.
  `docket context` moves out of `docket/cli/query.py`, the completion scripts
  and `docket update` out of `docket/cli/admin.py`. Every public name still
  imports from the module it did before, so no caller changes.

## [0.16.0] - 2026-09-19

### Added

- `docket feature`, a work-tracking store kept beside the decision ledger in
  `.docket/features.jsonl`. `start`, `list`, `show`, `note`, `amend`, `done`
  and `abandon` record a named piece of work, its declared paths, and its
  lifecycle. `done` classifies the branch's realized change set against the
  declared paths and closes the feature; `docket check` reports corruption in
  the feature store alongside the ledger. The feature store never reads or
  writes a ledger record.
- `docket feature brief` derives which ledger records govern a feature from
  its declared paths and prints them strongest first, each with the strength,
  specificity, and match count that ranked it. `feature amend --include` and
  `--exclude` correct the derived set by ID, and `docket check` validates
  every ID named there against the ledger.
- `feature list` and `feature show` report `blocked` in place of the declared
  status when an attached decision derives as blocked, the same prerequisite
  relation `docket context` computes for `docket decision`. An open question
  in the feature's scope never blocks it.
- `feature done --held CSV` and `--failed CSV` record a verdict on a claim the
  realized change set touched; an attached claim with no verdict is recorded
  `unanswered`. A `--failed` claim prints the `docket claim --supersedes`
  command that would record the correction and stops. The feature store
  still never writes to the ledger. `done` also prints an advisory naming
  another open feature whose declared paths overlap the realized change set.
- `.gitattributes` marks `.docket/*.jsonl` `merge=union`, so two branches'
  ledgers or feature stores merge by keeping every line from both sides.
  `docket feature remap MAPFILE` and `docket rebase --emit-map PATH` repoint
  a feature's `include`/`exclude` lists through the ID map a rebase produces,
  each correction a new append-only `amend` event.
- `docket feature gc --expire DAYS` archives closed features
  into `.docket/archive/features-<revision>.jsonl`, following d96's
  mechanism: a record count never triggers the move, only invoking `gc`
  does. `docket feature show` reads the archive when a slug or ID misses in
  the live store.
- `docket context` names the active feature above the record selection: its
  slug, state, declared intent, and highest-ranked attached records, taking
  a bounded share of the same character budget. A repository with no
  feature store, no git, or a store that fails to read produces no header.
- `skills/docket-feature/SKILL.md`, a second skill covering when to start a
  feature, resuming with `docket feature brief`, and closing with `docket
  feature done`. `skills/docket/SKILL.md` stays about recording.

## [0.15.0] - 2026-09-16

### Added

- `gg` and `G` jump the graph viewer to the first and last record. `g` is a
  prefix key, and any other key clears it and then runs normally.
- `s` cycles the graph viewer's sort field through ledger order, id, timestamp,
  kind and state, and `r` reverses the direction. A sort reorders roots only and
  each subtree moves with its root, so a support tree stays readable. The
  selection follows the record across a re-sort, and the footer names the active
  field and direction.

## [0.14.0] - 2026-09-15

### Added

- Recording hints on stderr when `--scope`, `--alternative`, `--rationale` or
  `--cost` is empty, and records the entry anyway. Each field is legitimately
  empty for some records. Scope leads the list, because a record with no scope
  competes for room in every briefing.

### Changed

- Recording refuses a decision whose `alternatives` only repeat the choice, and
  one whose `rationale` restates the choice or the question. The old rule
  required the choice to appear in `alternatives`, which made a one-element list
  the shortest valid answer; 38 of the first 90 records took it. An empty
  `alternatives` list is legal, so no recorder needs to invent a contender that
  never existed. The checks run when a record is written. Validation on read
  still checks structure alone, so an existing ledger reads unchanged.

### Fixed

- A reinstall over an existing checkout failed. The installer refused to swap
  when both the old tree and the staged clone held `.docket`, which every clone
  has carried since the repository began tracking its own ledger. The installed
  ledger now replaces the clone's outright.
- The ledger guard hook let `git restore`, `git checkout --`, `find -delete`,
  `sort -o`, `sort -uo` and `uniq IN OUT` through. Those four programs sat on
  the reader allowlist by name, and their arguments went unread.
- `docket migrate` folded the choice into `alternatives` for every decision. A
  schema 1 ledger records no alternatives, so the result was a one-element list
  carrying nothing. Migrated decisions now get an empty list.
- `docket update` lost a custom installation. It passed only `--update` to the
  downloaded launcher, which runs outside the checkout and could resolve neither
  the checkout nor the recorded prefix.

## [0.13.0] - 2026-09-14

### Added

- `docket construct` reaches OpenAI and Anthropic directly, alongside OpenRouter
  and Gemini. `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` select them, and
  `DOCKET_CONSTRUCT_PROVIDER` names one when several keys are set.
  An Anthropic key needs the `anthropic` SDK rather than `openai`. Anthropic's
  OpenAI-compatible layer ignores `response_format`, so a Claude key reached
  that way returns prose and every record fails the schema check.
- `docket construct --install-sdk PROVIDER` puts that provider's SDK in a
  virtualenv under the global store, and `--remove-sdk` deletes it. Nobody types
  a `pip install` any more. The installer offers the step during setup and takes
  `--construct PROVIDER` unattended; it records the choice in `.docket-managed`,
  so `--update` refreshes the SDK and uninstall removes it. The step needs `uv`,
  and a missing `uv` is a note rather than a failed install. A package already
  importable in your environment still wins over the virtualenv.
- `just fmt` and `just lint` format, lint and type check both languages, and CI
  runs the same commands at the same pinned versions. Python uses `ruff` and
  `pyrefly`, configured in `ruff.toml` and `pyrefly.toml`; Go uses
  `golangci-lint`, configured in `.golangci.yml`. Everything runs through `uvx`
  and `go run`, so none of it is an install requirement.

### Fixed

- `atomicInstallViewer` dropped the error from `Close()` on the temporary file
  it had just written. Buffered writes flush at close, so a full disk could lose
  the graph viewer binary and report success.

## [0.12.0] - 2026-09-14

### Added

- `docket construct PATHS` reads a project's written history and stages ledger
  proposals from it, so a project with years of documents does not start from an
  empty ledger. It never writes to the ledger: `--review` prints the proposals
  with the source line each one quotes, and `--accept` appends the ones marked
  accepted. Acceptance is the approval the ledger records.
  Every record carries a verbatim anchor, which keys it across runs and gives a
  reviewer a line to open. Scope and dates resolve locally, and a date comes from
  the document, then its filename, then git. A second pass proposes support,
  supersession and contradiction between records; a contradiction becomes a
  question naming both, never a silent supersession.
  The command needs the `openai` SDK and an `OPENROUTER_API_KEY` or
  `GEMINI_API_KEY`. It is the only command with a dependency: every other
  command, and the SessionStart hook, run without one.

### Changed

- The modules under `lib/` are now the `docket` package, and `bin/docket` is a
  launcher. Every import is absolute against one canonical name, which removed
  two `try/except ImportError` pairs and two runtime `importlib` calls that
  mutated `sys.path`. Code importing `lib.docket_ledger` or `docket_ledger`
  imports `docket.ledger` instead.

## [0.11.0] - 2026-09-13

### Added

- `docket update` refreshes an installer-managed checkout, or prints the
  plugin manager command for a plugin-only install. `installer/install.py
  --update` now refreshes an installed Claude Code or Codex plugin as well,
  instead of leaving harness configuration untouched.
- `docket` checks for a newer release once a day, in a detached background
  process, and prints a notice above the context briefing when one is
  available. `DOCKET_NO_UPDATE_CHECK=1` disables the check and the notice.

## [0.10.0] - 2026-09-13

### Added

- `docket check` reports every fault in a ledger with its line number:
  malformed, duplicate, out-of-order, and invalid records. A normal read stops
  at the first fault, which hides the rest of the damage a bad merge did.
- `docket rebase OTHER` appends the records `OTHER` holds past the shared
  prefix, each under a fresh ID, and rewrites the references inside that tail.
  Use it to resolve the git conflict two recording branches produce. `--dry-run`
  prints the ID map and writes nothing.
- `docket init` writes `.docket/.gitignore` with `*.lock`, so a team that
  commits `.docket/` does not commit the append lock. An existing file is left
  alone.
- `docket migrate` converts a pre-0.8 ledger to schema 2. It derives the record
  kinds from the old state field, keeps the original at `ledger.jsonl.schema1`,
  and accepts a hand-edited classification map through `--emit-map` and `--map`.
  It rewrites a `supersedes` edge into a question as an `answers` edge, and
  drops a support edge into a question, warning about both on stderr.
- `docket context` explains a blocked decision. Each chain of prerequisites
  prints as one `blocked:` line that names every step and the reason the last
  one is unavailable. `blocked_by` flattens a chain into one list, so it could
  not tell a two-step chain from two direct prerequisites. A record on such a
  chain joins the full-text tier directly after the decision it blocks.
- `docket context` closes with a coverage line. It reports whether the task
  matches and their prerequisites all reached the full-text tier, or how many
  stayed in the index.
- `docket context --since RECORD_ID` reports what changed after a baseline
  record: the records added since, and the records that lost availability since.
  The header now prints `latest: ID@DIGEST`, and `--since` accepts that pair.
  `docket rebase` renumbers a tail, so the digest catches a baseline ID that now
  names a different record. An unknown or stale baseline falls back to a full
  briefing.
- `docket show ID --at RECORD_ID` prints the record as history stood at that
  record. A supersession or an answer recorded later does not appear.
- `experiments/context-format/` and `experiments/context-scale/` measure what a
  briefing costs, by format and by ledger size.

### Changed

- `docket context` caps the index at `index.max_lines` records, 40 by default,
  and closes it with a count and `docket list`. A thousand-record ledger listed
  a thousand identifiers, which no agent can act on.
- An explicit `--query` now outranks a glob or directory file scope. An exact
  path scope still wins. A query states the task, and a scope derived from the
  working tree guesses at it.
- `docket context` scopes from the last commit when the working tree is clean.
  The first briefing of a session followed a commit, so it carried no file scope
  at the moment an agent was about to continue that work. A repository with no
  commits stays unscoped.
- A file scope too long for the header prints as a count and a digest, so a
  briefing scoped by more than about six paths stays reproducible from its own
  header.

### Fixed

- A briefing past about 1100 records carried no record content at all. The
  budget gate charged one bare name for every current record before admitting
  anything, and those names exceeded the target on their own, so every record
  was refused. A 3000-record ledger rendered 3000 IDs and no records.
- Reads hold a shared lock on the ledger, so a reader no longer sees a
  half-written line and fails on invalid JSON. Writers already held an exclusive
  lock.
- `docket context` is linear in ledger size. Four separate paths cost O(n
  squared): the in-degree scan, the per-record re-derivation of the validation
  prefix, the admission trial that rendered the whole briefing per candidate,
  and the per-candidate copies of the footer sets. A 1000-record ledger took
  5.8s and a 10000-record ledger did not finish inside 562s; they now take 0.3s
  and 1.8s. `docket check` shed the same prefix rebuild.
- Every command that meets a legacy ledger now names `docket migrate` instead
  of a script path that an installed Docket does not ship.

## [0.9.0] - 2026-09-12

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

[Unreleased]: https://github.com/NovusEdge/docket/compare/v0.17.0...HEAD
[0.17.0]: https://github.com/NovusEdge/docket/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/NovusEdge/docket/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/NovusEdge/docket/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/NovusEdge/docket/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/NovusEdge/docket/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/NovusEdge/docket/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/NovusEdge/docket/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/NovusEdge/docket/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/NovusEdge/docket/compare/v0.8.1...v0.9.0
[0.8.1]: https://github.com/NovusEdge/docket/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/NovusEdge/docket/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/NovusEdge/docket/compare/v0.6.3...v0.7.0
[0.6.3]: https://github.com/NovusEdge/docket/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/NovusEdge/docket/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/NovusEdge/docket/releases/tag/v0.6.1
