# Feature tracking

`.docket/features.jsonl` records work in flight: a named piece of work, the
paths it declares, and what it actually changed. It sits beside
`ledger.jsonl`, resolves the same way (a project store under `.docket/` when
one exists, otherwise the per-repository store under `~/.claude/docket/`),
and `docket init` moves both files together.

The ledger records what was settled. It does not record which piece of work
is underway, what that work intended, or which commits belong to it. The
feature store answers those three questions and never writes to the ledger.

## Events

Like the ledger, the store is append-only: one JSON object per line, and
current state is a projection over the whole log, never an edit in place.

| Event | Required fields | Effect |
|---|---|---|
| `start` | `slug`, `text`, `paths` | Creates the feature. Records the fork-point `base` and the current `branch`. |
| `amend` | `slug`, one changed field | Replaces `status`, `paths`, `intends`, `include` or `exclude` wholesale. |
| `note` | `slug`, `text` | Appends a dated line to the feature's log. |
| `done` | `slug` | Closes the feature and records the realized change set. |
| `abandon` | `slug`, `text` | Closes the feature with no realized change set. |

`start` on a slug that already projects to an open feature is refused.

## Status versus state

A feature carries a declared `status` and projects to a `state`. The status is
`active` (the default), `paused`, or `review`. `done` and `abandoned` are not legal
values for `status`: they arrive only through the `done` and `abandon`
events, so nothing can type a feature closed against its own log.

State resolves in order, first match winning: a `done` event beats an
`abandon` event beats the declared `status`.

## Slugs are refs, IDs are permanent

A slug behaves like a branch name: unique among open features, reusable once
closed. The `f`-prefixed ID (`f1`, `f2`, ...) is the permanent address, the
way a SHA outlives a deleted branch. `docket feature show <slug>` resolves
the open feature; when only closed runs match, it exits 1 and lists their
IDs.

The composite form `f7@6f0898e2` appends eight characters of the feature's
`base` SHA. It appears only when two features collide on the same bare ID,
such as after a union merge. Git abbreviates a SHA the same way, only once it
becomes ambiguous.

## Commands

```
docket feature start <slug> --text TEXT --path GLOB [--path GLOB] [--intends TEXT]
docket feature list [--state STATE] [--json]
docket feature show <slug|id> [--json]
docket feature note <slug> TEXT
docket feature amend <slug> [--status STATUS] [--path GLOB] [--intends TEXT] [--include CSV] [--exclude CSV]
docket feature done <slug> [--held CSV] [--failed CSV]
docket feature abandon <slug> --text REASON
docket feature brief [<slug|id>]
docket feature remap MAPFILE
```

```
$ docket feature start opencode-discovery \
    --text "Installer places the OpenCode plugin where discovery finds it" \
    --path installer/**
f1 opencode-discovery

$ docket feature note opencode-discovery "confirmed the plugin path with a fresh install"

$ docket feature amend opencode-discovery --status paused

$ docket feature list
f1    paused     opencode-discovery       Installer places the OpenCode plugin...

$ docket feature done opencode-discovery
f1 done: 2 intentional, 1 outside
  outside declared paths: docs/random-note.md

$ docket feature abandon some-other-slug --text "superseded by a different approach"
```

## The fork-point base and the change set

`start` records `base` as the merge base with the default branch. HEAD would be
wrong: a feature declared partway through work still captures everything the
branch has done. On the default branch itself, `base` is HEAD and `start` warns
that there is no fork point.

`done` walks the branch's own commits with `git log --first-parent --no-merges
-M base..HEAD`, then classifies each changed path against the feature's
declared `paths`, using the same matcher `docket context` uses to select
records.

A plain two-tree diff cannot answer this. `base` is an ancestor of HEAD, so
`base...HEAD` collapses to two dots and carries in every file the default
branch gained after the fork. `--first-parent` keeps the walk on this branch's
line, so a merged-in default branch arrives through a second parent and never
counts. `--no-merges` drops the merge commits, which also drops any conflict
resolution made inside one.

Run `done` before squashing or rebasing the branch: once `base` is no longer
an ancestor of HEAD, `done` refuses and names the stale SHA.

A declared path must contain a `/` or a glob character. The shared matcher
skips a bare word, so `--path Makefile` or `--path installer` would match
nothing; `start` and `amend` refuse both and tell you to write `installer/**`.

## The brief

`docket feature brief [SLUG_OR_ID]` derives which ledger records govern a
feature from its declared paths, without any hand-drawn link between the two
stores. Paths expand against the files git tracks, and every ledger record
whose scope covers one of those files attaches, strongest match first.

Each attached record's line names why it attached: `strength` is the same
scope score `docket context` ranks records by, `specificity` is the length of
the matching glob's literal prefix (a record scoped to
`installer/planner.go` outranks one scoped to `installer/**` even at equal
strength), and `matches` is how many of the feature's files that glob covers.
A rank you disagree with is visible on the line that produced it, and
`docket feature amend --exclude ID` drops a record the globs pulled in
wrongly; `--include ID` attaches one the globs miss.

```
$ docket feature brief opencode-discovery
### f1 | opencode-discovery [active] Installer places the OpenCode plugin...
intends: the plugin loads
paths: installer/**
d81 | decision | ... [strength 1000, specificity 20, matches 1]
q75 | question | ... [strength 1000, specificity 10, matches 4]
```

## Blocked

`blocked` replaces the declared status on `feature list` and `feature show`
when an attached decision derives as blocked. That is the same prerequisite
relation `docket context` already computes for every decision (d109). An open question
in the feature's scope never blocks it: scope overlap is a transient property
that would fire on nearly every feature merely because some question happens
to be open in its files today. Work actually stalled on a question is
declared `paused` instead.

## Claim verification at `done`

`done` asks only about claims whose scope intersects the change set the
branch actually realized; a claim about code the work never touched has
gained no new evidence either way. `--held CSV` and `--failed CSV` mark
verdicts; anything else attached comes back as `unanswered`. For each
`--failed` claim, `done` prints the `docket claim ... --supersedes` command
that would record the correction and stops. **It never writes the disputing
record for you.** The three verdict lists are stored on the `done` event and
read back with `feature show --json`.

## Branch convergence

Two active features on different branches are allowed to declare overlapping
paths, the way branches diverge freely and conflict only at merge; `done`
prints an advisory naming another open feature whose declared paths overlap
the realized change set, without changing its exit code.

`.gitattributes` marks both `.docket/*.jsonl` stores `merge=union`, so a
branch merge keeps every line from both sides instead of conflicting on
append-only files. A union merge can duplicate `f` IDs and leave an `include`
or `exclude` list naming a ledger ID a rebase renumbered.
`docket feature remap MAPFILE` repoints those lists through the ID map
`docket rebase --emit-map PATH` writes, one new `amend` event per feature that
needs one. Remapping never edits a written `start` or `amend` line in place,
the way `hooks/guard_ledger.py` requires for every append-only store.

## What is not here yet

Stage 2 ships the brief, derived `blocked`, claim verification at `done`, and
branch convergence. Archival (`docket feature gc`) and a `docket context`
header naming the active feature remain unbuilt.
