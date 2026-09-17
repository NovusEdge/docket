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

A feature carries a declared `status` — `active` (the default), `paused`, or
`review` — and projects to a `state`. `done` and `abandoned` are not legal
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
such as after a union merge — the same way git abbreviates a SHA only once
it becomes ambiguous.

## Commands

```
docket feature start <slug> --text TEXT --path GLOB [--path GLOB] [--intends TEXT]
docket feature list [--state STATE] [--json]
docket feature show <slug|id> [--json]
docket feature note <slug> TEXT
docket feature amend <slug> [--status STATUS] [--path GLOB] [--intends TEXT]
docket feature done <slug>
docket feature abandon <slug> --text REASON
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

`start` records `base` as the merge base with the default branch, not HEAD —
a feature declared partway through work still captures everything the branch
has done. On the default branch itself, `base` is HEAD and `start` warns that
there is no fork point.

`done` diffs `base...HEAD` (three dots, so a branch that merged the default
branch in does not pick up its files) and classifies each changed path
against the feature's declared `paths`, using the same matcher `docket
context` uses to select records. Run `done` before squashing or rebasing the
branch: once `base` is no longer an ancestor of HEAD, `done` refuses and
names the stale SHA.

## What is not here yet

Stage 1 ships the store, the five events, declared status, and outcome
classification at `done`. The `include`/`exclude` fields exist in the schema
but carry no CLI flags yet, and there is no derived `blocked` state and no
claim verification at `done` — those, along with the ledger-scoped brief,
arrive in stage 2.
