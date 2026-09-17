---
name: docket-feature
description: Track a piece of work in flight against the ledger, from start to done, and know when a feature is worth declaring.
---

# docket-feature

The feature store tracks work in flight: what a piece of work intends, the
paths it declares, and what it actually changed. It never writes to the
ledger. Use the absolute command path supplied by the session context. The
examples use `docket` for readability.

## When to start a feature

Start one before work that spans more than one session, or whose blast radius
is worth declaring: a change that touches several files, crosses a module
boundary, or another agent might pick up later. Do not start one for a
one-line fix or a change you will finish and commit in this turn.

## Starting work

```sh
docket feature start opencode-discovery \
  --text "Installer places the OpenCode plugin where discovery finds it" \
  --path installer/**
```

A declared path needs a `/` or a glob character. `--path installer` or
`--path Makefile` matches nothing and `start` refuses both.

## Resuming work

Run `docket feature brief` first, before anything else, when picking up a
feature already started:

```sh
docket feature brief opencode-discovery
```

The brief derives which ledger records govern the feature from its declared
paths and prints each one with three numbers:

- `strength` is the same scope score `docket context` ranks records by.
- `specificity` is the length of the matching glob's literal prefix; a record
  scoped to one file outranks one scoped to a directory glob even at equal
  strength.
- `matches` is how many of the feature's files that glob covers.

A rank you disagree with is visible on the line that produced it. Correct it
with amend:

```sh
docket feature amend opencode-discovery --exclude d81
docket feature amend opencode-discovery --include q75
```

## Status and blocked

`docket feature list` and `docket feature show` report `blocked` when an
attached decision derives as blocked, the same prerequisite relation
`docket context` computes for every decision. An open question in the
feature's scope does not block it on its own; scope overlap alone would fire
on nearly every feature. Work stalled on a question is declared `paused` by
hand:

```sh
docket feature amend opencode-discovery --status paused
```

## Closing work

Run `done` before squashing or rebasing the branch. Once the fork point is no
longer an ancestor of HEAD, `done` refuses and names the stale SHA.

```sh
docket feature done opencode-discovery
```

`done` prints two change-set lists: paths the branch changed that the feature
declared, and paths it changed outside them. A file outside the declared
paths is not an error, it is a fact to notice before merging.

## The claim prompt at done

`done` asks only about claims whose scope intersects the paths the branch
actually changed; a claim about code the work never touched gained no new
evidence. Mark verdicts with `--held` and `--failed`:

```sh
docket feature done opencode-discovery --held c12 --failed c9
```

For each `--failed` claim, `done` prints the `docket claim ... --supersedes`
command that would record the correction, then stops. Docket never writes
that record. Run the printed command yourself.
