# Feature tracking

`.docket/features.jsonl` records work in progress: its name, declared paths,
and actual changes. It sits beside `ledger.jsonl` and follows the same location
rules: a project store under `.docket/` when one exists, otherwise the
per-repository store under `~/.claude/docket/`. `docket init` moves both files
together.

The ledger records what was settled. It does not record which piece of work
is underway, what that work intended, or which commits belong to it. The
feature store answers those three questions and never writes to the ledger.

## Events

Like the ledger, the store is append-only, with one JSON object per line.
Docket derives the current state from the whole log.

| Event | Required fields | Effect |
|---|---|---|
| `start` | `slug`, `text`, `paths` | Creates the feature. Records the fork-point `base` and the current `branch`. |
| `amend` | `slug`, one changed field | Replaces `status`, `paths`, `intends`, `include` or `exclude` wholesale. |
| `note` | `slug`, `text` | Appends a dated line to the feature's log. |
| `done` | `slug` | Closes the feature and records the realized change set. |
| `abandon` | `slug`, `text` | Closes the feature with no realized change set. |

`start` refuses a slug that already belongs to an open feature.

## Status versus state

A feature has a declared `status` and a derived `state`. The status is
`active` (the default), `paused`, or `review`. `done` and `abandoned` are not legal
values for `status`: they arrive only through the `done` and `abandon`
events, so closing a feature requires a corresponding event in its history.

State resolves in this order: a `done` event takes precedence over an
`abandon` event, which takes precedence over the declared `status`.

## Slugs are refs, IDs are permanent

A slug behaves like a branch name: unique among open features, reusable once
closed. The `f`-prefixed ID (`f1`, `f2`, ...) permanently identifies the
feature. `docket feature show <slug>` resolves the open feature; when only
closed runs match, it exits 1 and lists their IDs.

The composite form `f7@6f0898e2` appends eight characters of the feature's
`base` SHA. It appears only when two features collide on the same bare ID,
such as after a union merge.

## Commands

```
docket feature start <slug> --text TEXT --path GLOB [--path GLOB] [--intends TEXT]
docket feature list [--state STATE] [--json]
docket feature show <slug|id> [--json]
docket feature note <slug> TEXT
docket feature amend <slug> [--status STATUS] [--path GLOB] [--intends TEXT] [--include CSV] [--exclude CSV] [--clear FIELD]
docket feature done <slug> [--held CSV] [--failed CSV]
docket feature abandon <slug> --text REASON
docket feature brief [<slug|id>]
docket feature remap MAPFILE
docket feature gc [--expire DAYS]
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

`start` records `base` as the merge base with the default branch. This includes
earlier branch work when you declare a feature partway through a task. On the
default branch itself, `base` is HEAD and `start` warns that there is no fork
point.

`done` walks the branch's own commits with `git log --first-parent --no-merges
-M base..HEAD`, then classifies each changed path against the feature's
declared `paths`, using the same matcher `docket context` uses to select
records.

A diff between `base` and HEAD would also include changes merged from the
default branch. Because `base` is an ancestor of HEAD, `base...HEAD` gives
the same result as `base..HEAD`. `--first-parent` follows this branch's history
and excludes commits brought in through a merge's second parent. `--no-merges`
excludes merge commits, including any conflict resolution made in them.

Run `done` before squashing or rebasing the branch: once `base` is no longer
an ancestor of HEAD, `done` refuses and names the stale SHA.

A declared path must contain a `/` or a glob character. The shared matcher
skips a bare word, so `--path Makefile` or `--path installer` would match
nothing; `start` and `amend` refuse both and tell you to write `installer/**`.

## The brief

`docket feature brief [SLUG_OR_ID]` finds the ledger records that apply to a
feature by matching its declared paths. Paths expand against the files Git
tracks, and every ledger record whose scope covers one of those files attaches,
strongest match first.

Each attached record's line names why it attached: `strength` is the same
scope score `docket context` ranks records by, `specificity` is the length of
the matching glob's literal prefix (a record scoped to
`installer/planner.go` outranks one scoped to `installer/**` even at equal
strength), and `matches` is how many of the feature's files that glob covers.
Use these values to inspect the ranking. `docket feature amend --exclude ID`
removes an incorrectly matched record; `--include ID` attaches one the globs
miss.

Both flags replace the whole list. To undo an override rather than change it,
run `docket feature amend <slug> --clear include` (or `--clear exclude`, or
`--clear intends`). These flags explicitly clear a field; omitting the field
from an amendment preserves its value.

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
when an attached decision is blocked by its prerequisites. This uses the same
prerequisite rules as `docket context`. An open question in the feature's scope
does not block it: sharing a scope does not establish that the work depends on
the answer. Set the status to `paused` when work is waiting on a question.

## Claim verification at `done`

`done` asks only about claims whose scope intersects the branch's actual
changes. Claims about untouched code are outside this check. `--held CSV`
and `--failed CSV` mark verdicts; anything else attached comes back as
`unanswered`. For each
`--failed` claim, `done` prints the `docket claim ... --supersedes` command
that would record the correction and stops without writing that record.
The three verdict lists are stored on the `done` event and read back with
`feature show --json`.

## Branch convergence

Two active features on different branches may declare overlapping paths.
`done` prints an advisory when another open feature's declared paths overlap
the actual changes. The advisory does not change the exit code.

`.gitattributes` marks both `.docket/*.jsonl` stores `merge=union`, so a
branch merge keeps every line from both sides instead of conflicting on
append-only files. A union merge can duplicate `f` IDs and leave an `include`
or `exclude` list naming a ledger ID a rebase renumbered.
`docket feature remap MAPFILE` repoints those lists through the ID map
`docket rebase --emit-map PATH` writes, one new `amend` event per feature that
needs one. Remapping preserves the original `start` and `amend` lines.

## The briefing header

`docket context` names the active feature above the record selection: its
slug, state, and declared intent, followed by its three highest-ranked
attached records. The header takes a reserved share of the same character
budget as the record selection, at most a quarter of the total. The remaining
budget is available for records. If the repository has no feature store or no
Git metadata, or the feature store cannot be read, the briefing omits the
header and continues.

## Archival

Run `docket feature gc` to move closed features' events into
`.docket/archive/features-<revision>.jsonl`. Archiving runs only when invoked;
the record count does not trigger it. `--expire DAYS` limits the selection to
features closed more than that many days ago. It does not schedule an archive.

Archiving never frees the ID. A new feature's number starts above the highest
ID any archive holds, so a citation to an archived feature keeps pointing at
that feature.

```
$ docket feature gc
docket: archived 4 feature event(s) to .docket/archive/features-9f2ab1c4e8a0.jsonl
```

`docket feature show` reads the archive when a slug or ID misses in the live
store, so a closed feature stays retrievable after `gc` moves it.
