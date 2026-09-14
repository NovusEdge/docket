# Constructing on existing projects

A project that already has years of design notes starts with an empty ledger.
`docket construct` reads those documents and proposes records from them, so you
begin with the decisions your team already made instead of a blank file.

Construct never writes to your ledger. It stages proposals, you read them, and
you accept the ones that are right. That acceptance is what the ledger records.

## Before you start

Construct is the only command that needs a dependency and an API key. Every
other command, and the session hook your agent runs, work without either.

Set one key. An OpenRouter key reaches every provider through one endpoint:

```sh
export OPENROUTER_API_KEY=...
```

A `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` works instead and
calls that provider directly. The first one set wins, in that order;
`DOCKET_CONSTRUCT_PROVIDER` names one explicitly.

Install the SDK your key needs:

```sh
docket construct --install-sdk openrouter
```

That builds a virtualenv under the global store and puts one package in it. It
uses `uv`, so install [uv](https://docs.astral.sh/uv/) first if you do not have
it. The installer offers the same step during setup, and
`--construct <provider>` selects it unattended.

Every provider except Anthropic is reached through the `openai` package.
Anthropic needs its own, because its OpenAI-compatible layer ignores
`response_format`, which is how construct asks for the schema.

A package you installed yourself wins over the virtualenv, so an existing
`openai` in your environment keeps working untouched.

See [Environment variables](environment.md) for the model and endpoint
overrides.

## See what it would read

Run this first. It lists the documents and calls nothing, so it needs no key:

```sh
docket construct --dry-run context/decisions context/specs
```

Name directories or single files. Construct reads `*.md` under a directory, at
any depth.

## Stage the proposals

```sh
docket construct context/decisions context/specs
```

Each document becomes one call. The run prints what it found and what it
refused:

```
read 42 documents
context/decisions/2026-06-18-coherence-layer.md: 15/15 anchors matched
context/specs/auth.md: dropped a record, its anchor quotes no line in the document
link: 2 batches
link: kept 18 edges
link: asked 3 questions about contradictions
docket: staged 412 proposals in .docket/proposed.jsonl
```

Every proposal carries an **anchor**: one line copied from the source document.
A proposal whose anchor matches no line in that document is dropped, because
nothing ties it to something you wrote.

The **anchor match rate** tells you whether the run is trustworthy. A document
reporting 15/15 was read closely. One reporting 4/12 was paraphrased, and every
record from it needs your eye before you accept it.

A second pass reads the whole proposal set and proposes the relations between
records: which one grounds another, which replaces another, and which two
disagree. A disagreement it cannot settle becomes a question naming both
records, never a silent replacement.

## Read them

```sh
docket construct --review
```

Proposals group by source document, strongest first:

```
# scope resolves: 221/396
# staged: 412

## context/decisions/2026-06-18-coherence-layer.md
  decision (high)
    How is audit-repair checking arranged?
    choice: Tiered by epistemic layer
    scope: src/coherence/**
    anchor: **Decision:** Option B - tiered checking by layer.
    key: 5c644f951a7b
```

The anchor is the line to open. Read the record against it and decide whether it
says what the document says.

`scope resolves` is the number to watch. A record whose scope matches no file in
the repository can never reach a briefing, and those sort to the bottom of each
group marked `[unresolved scope]`. A run resolving most of its scoped records
points at live code. A run resolving few of them describes code that is gone,
and the answer is to narrow what you feed it rather than to accept the result.

A record with a stale path is not always dead. Sometimes it is the only
surviving account of a rename, which is why construct never drops one.

## Accept what is right

Mark a proposal by changing its `state` to `accepted` in
`.docket/proposed.jsonl`. Leave the rest alone, or set `rejected` for the ones
you never want to see again.

```sh
docket construct --accept
```

This is the only step that touches your ledger. It allocates real record IDs,
rewrites the relations to use them, and appends through the ordinary writer, so
numbering and locking behave as they do for a record you write by hand.

Take one document at a time:

```sh
docket construct --accept --source context/decisions/auth.md
```

Acceptance is resumable. Each proposal carries its own state, so you can stop
after one sitting and continue later. A review of several hundred proposals that
must finish in one pass gets rubber-stamped instead of read.

Accepted records name their source document in the rationale and record
`docket-construct` as the author, so a later reader can tell a constructed record
from one a person wrote at the time.

A record whose supporting record you did not accept is skipped rather than
written without it. Its grounds are part of what it says.

## Running it again

Re-running is safe. Construct keys each proposal on its source path and its
anchor, so a record you already accepted stays accepted even though the model
words it differently on the second run.

Editing a source line changes that key, and the record returns to review. The
text you accepted it against no longer exists.

## What it does not do well

Construct finds few supersessions. It relates records in batches that keep each
document whole, and two documents on the same subject written months apart often
land in different batches, which is exactly where a supersession lives. Record
those by hand as you meet them.

Commit messages are not read by default. Nobody has measured what they yield.

## Costs

One call per document, plus one per batch of about 120 proposals. Reading 400
documents of a few thousand words each costs well under a dollar on a fast
model. Cost is not the reason to narrow the input set. A low scope resolution
rate is.
