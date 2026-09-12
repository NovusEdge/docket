# Ledger reference

Docket 0.8.0 writes schema 2 records as append-only JSONL. Each non-empty line
contains one JSON object. Reads validate the complete file, so Docket reports
an invalid line or relation instead of silently dropping it.

## Record types

Every record has these required fields:

- `schema`: the schema number, which is `2` for this format.
- `kind`: `claim`, `decision`, or `question`.
- `id`: a type-prefixed record ID with a positive global sequence number.
- `text`: the proposition, commitment, or inquiry.
- `state`: the record's recorded workflow state.
- `ts`: the record timestamp string.
- `author`: the person or agent that recorded it.
- `session`: the recording session identifier, when available.
- `branch`: the repository branch, when available.

| Kind | Meaning | Recorded states | Type-specific fields |
|---|---|---|---|
| `claim` | A scoped proposition | `unassessed`, `accepted`, `disputed`, `rejected` | none |
| `decision` | A commitment to a choice | `adopted`, `revoked` | `choice`, `alternatives`, optional `decided_by` |
| `question` | An unanswered inquiry | `open` | none |

IDs use the type prefix and a positive global sequence number: `c1`, `d2`, and
`q3`. The sequence is shared across kinds, and gaps are allowed.

A question's recorded state remains `open`. A current accepted claim or
applicable adopted decision linked to it through `answers` gives it effective
state `resolved` in a derived view.

### Recorded, effective, and current state

- Recorded state is the value stored on the append-only line.
- Effective state changes from `open` to `resolved` for a question with a
  current accepted claim or applicable adopted decision answering it.
- Decision applicability is a separate derived result, exposed through
  `applicable` and `blocked_by`. The decision keeps its recorded state.
- Currentness identifies whether a later same-kind record supersedes the
  record. A superseded record remains available with its original line, state,
  and provenance, but it is not current support.

Acceptance and adoption are workflow statuses. Their values do not establish
that a claim is true or a decision is correct. Evidence supplies provenance;
the ledger does not guarantee its freshness or truth.

## Common fields

All records also contain these fields. Docket supplies empty strings or lists
when their CLI options are omitted, and sets `pinned` to `false`:

- `scope`: path patterns or component names used for context selection.
- `rationale`: the reasoning recorded with the record.
- `supports`: alternative sets of claims or decisions that support the record.
- `depends_on`: decision prerequisites.
- `answers`: declared links from a claim or decision to questions; a link
  resolves its target only when the source is current and is either an
  accepted claim or an applicable adopted decision.
- `supersedes`: same-kind records retired by this record.
- `evidence`: provenance objects attached to the record.
- `revisit`: a note about when or why to revisit the record.
- `cost_if_wrong`: the stated cost if the record is wrong.
- `pinned`: whether the record scores a fixed bonus in every briefing; defaults
  to `false`. A pin no longer outranks a better scope match.

Path scopes use normalized repository-relative paths. A scope containing a
slash or glob metacharacters uses `fnmatch`; a literal directory scope also
matches its descendants. A bare component name matches query text only and
does not create an implicit component-to-file mapping.

`evidence` is a list of objects. Each object requires a non-empty `ref` and may
include `checked_at` and `commit` strings. `author` identifies the recorder.
For decisions, `decided_by` can attribute the commitment to another person or
agent. Both values are self-reported; Docket does not authenticate these
identities.

## Relations

### Supports

`supports` is a list of non-empty ID lists:

```json
"supports": [["c1", "c2"], ["c3"]]
```

IDs in one inner list are conjunctive AND requirements. Inner lists are
alternative OR sets, so the example means `(c1 AND c2) OR c3`. These are
declared grounds. Docket does not verify the corresponding logical implications.
Only claims and decisions can be support targets.

### Decision prerequisites

`depends_on` is an operational relation for decisions. Its targets are claims
or decisions, and it has no OR interpretation.

A current adopted decision is applicable when all of these conditions hold:

- claim prerequisites are accepted and current;
- decision prerequisites are adopted, current, and applicable.

Otherwise the projected record contains `applicable: false` and `blocked_by`
with the unavailable prerequisites. Its recorded choice remains adopted, and a
blocked decision does not resolve a question.

### Answers and supersession

`answers` links a claim or decision to a question. A current accepted claim or
applicable adopted decision resolves its target in the projected view.

`supersedes` retires same-kind records. Docket rejects self-links, unknown or
later IDs, cross-kind supersession, and supersession of an already retired
record.

## Derived views

The validator preserves the original record. `project` adds:

- `recorded_state`;
- effective `state` for resolved questions;
- `retired_by` and `resolved_by`;
- `applicable` and `blocked_by` for decisions.

Retiring a record preserves its recorded state and the recorded states of
dependent decisions. Their applicability is recalculated, and any older
predecessor stays retired.

`show --json` exposes the original record and derived fields. `list --json`
returns machine-readable projected records. `graph` sends a version 2 projection
to the native viewer.

The graph projection keeps the legacy renderer keys `question`, `answer`,
`cost`, `sets`, and the deduplicated `supports` union, while adding typed
metadata and relation fields. `sets` preserves the complete AND/OR formula;
the union serves the renderer as a convenience.

## Bounded context

`docket context` renders projected records for a harness.

Every current record appears, in one of two tiers. The full-text tier holds
complete record blocks. The index tier names each remaining record on one line
with its ID, kind, state, and clipped text. An index line's length follows its
score, so a near miss carries more text than a distant record.

- The budget target is 8,000 characters.
- A record matching the task scope or query renders in full even past the
  target, up to three times it.
- `--max-chars` sets a hard ceiling instead, with a minimum of 512 characters.
- The budget includes the header, record blocks, index lines, warnings, and the
  retrieval footer.
- Docket keeps propositions and negations whole. Over the ceiling it shortens
  index lines, then trims the lowest-scoring ones, then lists bare IDs.

Records rank by an integer score over scope match strength, query term rarity,
position in the record sequence, pinning, and how many records point at the
record. A scope match outranks a text match, because a scope states where a
record applies. Each full-text record prints its score and components.

Docket then adds related records in both directions: grounds, prerequisites,
dependents, questions, and their answers. A related record inherits half its
parent's score per hop, and expansion stops when that falls under the floor.
`--all` asks for every record in the full-text tier, subject to the budget. A
record that does not fit still falls to an index line.

With no `--query` and no `--file`, Docket derives file scope from the working
tree's changed and untracked files. `--no-auto-scope` disables that, and
`--auto-scope` forces it alongside an explicit query.

The header includes ledger identity, a deterministic revision, and the latest
record ID. The footer reports tier counts, incomplete relation coverage,
evidence-provenance limits, and a `docket show ID --json` retrieval command.

Weights, budget, index detail, expansion decay, and the auto-scope cap come from
`.docket/config.toml` when it exists. See [the annotated example](config.example.toml).
A briefing rendered with tuned settings names them in its header, so its
ordering stays reproducible.

```sh
docket context
docket context --query "cache invalidation" --file src/cache.py --max-chars 4000
docket context --all --max-chars 12000
```

The renderer does not fetch evidence, call a tokenizer, infer truth, or
propagate state. Re-run the briefing after compaction or resume through the
harness's existing hook surface.

## Sharing a ledger

Writers on one host are safe. `append` allocates the record ID, validates, and
writes while holding an exclusive lock on `ledger.jsonl.lock`, so two processes
never claim the same sequence number. Readers take a shared lock on the same
file, so a read never sees a half-written line.

Two branches that both record produce a git conflict on the ledger, because
each branch appends different records after the same last line. Resolve the
conflict with `docket rebase`, not by hand and not with a union merge driver. A
union merge keeps both branches' lines, which leaves two records holding one ID.
Every command then fails, including the session hook.

To repair a divergence, recover the other branch's ledger file and run:

```sh
docket rebase ../other-branch/.docket/ledger.jsonl --dry-run
docket rebase ../other-branch/.docket/ledger.jsonl
```

Rebase finds the prefix both files share, then appends the other file's
remaining records under fresh IDs. References inside that tail follow the
renaming. References into the shared prefix stay valid, because prefix IDs never
move, and no prefix record can point into the tail: validation forbids forward
references. `--dry-run` prints the ID map and writes nothing.

Hand-resolving the conflict has one silent failure. Keeping branch A's `c46` and
branch B's `d47` leaves `d47` pointing at A's `c46`, which exists and has the
right kind. Validation passes and the reference means something nobody chose.
Nothing detects this afterwards. Use `docket rebase`.

When a ledger stops reading, run `docket check`. It reports every malformed,
duplicate, out-of-order, and invalid record with its line number, where a normal
read stops at the first fault.

Docket does not merge divergent decision trees semantically. Two branches that
decided the same question differently produce two adopted decisions after a
rebase. A person resolves that by superseding one of them.

## Migrating a schema-1 ledger

A schema-1 ledger typed a `settled`, `ruled-out`, or `open` state instead of a
`kind` and `state` pair. Every command that reads such a ledger fails with an
actionable error. Run `docket migrate` to convert it in place.

```sh
docket migrate
```

The command derives a classification map from the old state field alone:

| Schema 1 state | Kind | State |
| --- | --- | --- |
| `settled` | decision | adopted |
| `ruled-out` | decision | adopted |
| `open` | question | open |

`ruled-out` maps to an adopted decision, not a revoked one: it commits to not
doing something, and that commitment still applies. A revoked decision renders
as unavailable support, which would tell an agent to ignore a live constraint.

Migration keeps the original. The converted ledger replaces `ledger.jsonl`,
and the untouched schema-1 file survives at `ledger.jsonl.schema1`. A ledger
already at schema 2 exits clean and changes nothing. `--dry-run` prints the
derived conversion and writes nothing.

Two edge shapes are common in old ledgers and get fixed automatically:

- A `supersedes` edge that points at a question becomes an `answers` edge.
  Schema 2 does not let a question carry `answers`.
- A `because` edge that points at a question is dropped. Schema 2 has no
  relation for this. The old edge still shows up in `legacy` metadata.

The command prints a warning line for each fix.

One case still stops the migration: a `settled` or `ruled-out` record with no
answer. There is no text to build a `choice` from. It prints the affected
records and a recovery: derive a map to a file, edit it, then apply it
explicitly.

```sh
docket migrate --emit-map map.json
# edit map.json by hand
docket migrate --map map.json
```
