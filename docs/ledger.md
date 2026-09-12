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
- `pinned`: whether the record receives priority in unscoped context; defaults
  to `false`.

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

- The default budget is 8,000 characters.
- The minimum accepted budget is 512 characters.
- The budget includes the header, complete record blocks, warnings, and
  retrieval footer.
- Docket keeps propositions and negations whole when it reaches the budget.

With no task query or file scope, startup context ranks pinned records first.
With a task query or `--file` scope, matching text and paths rank before
unrelated pins. Docket then adds bounded directly related records in both
directions: grounds, prerequisites, dependents, questions, and their answers.

At most 64 related records are admitted, and only after the selected record
fits. Pins break ties between equally relevant records. `--all` removes
relevance filtering while keeping the budget.

The header includes ledger identity and a deterministic revision. The footer
reports omitted and unrelated counts, incomplete relation coverage,
evidence-provenance limits, and a `docket show ID --json` retrieval command.

```sh
docket context
docket context --query "cache invalidation" --file src/cache.py --max-chars 4000
docket context --all --max-chars 12000
```

The renderer does not fetch evidence, call a tokenizer, infer truth, or
propagate state. Re-run the briefing after compaction or resume through the
harness's existing hook surface.

## Explicit migration from schema 1

Schema 1 reads fail with an actionable migration error. Migration is a separate
operation. It never overwrites the source or an existing destination.

1. Create a classification map.

   The map needs one JSON entry for every source ID. Each entry must choose
   `kind`, `state`, and `text`; Docket does not infer a type from English prose.

   For a source ledger at `old/ledger.jsonl`, create `map.json` with entries
   such as:

   ```json
   {
     "d17": {
       "kind": "decision",
       "state": "adopted",
       "text": "Which database should the service use?",
       "choice": "Postgres",
       "alternatives": ["Postgres", "SQLite"],
       "supports": [["d10"]],
       "answers": [],
       "supersedes": []
     }
   }
   ```

2. Run the standalone migration tool with a new destination:

   ```sh
   python3 scripts/migrate_ledger.py old/ledger.jsonl \
     --map map.json \
     --output .docket/ledger-v2.jsonl
   ```

   The tool validates every source relation and every mapped record before
   opening the destination with exclusive-create semantics. It rewrites
   relation IDs through the map, retains source text and relation treatment in
   `legacy` metadata, and leaves the source intact. A source `because` list
   maps to `supports` unless an explicit override is supplied. Cross-kind
   supersession or an old line that needs to become a question answer requires
   explicit relation overrides; the tool refuses silent edge loss. A question
   mapping uses recorded state `open`, even when later answer links give it
   derived state `resolved`.

3. Review and activate the destination.

   Keep the original ledger and classification map with the migration review.
   Switch the active project ledger only after the destination passes the
   validator and its record and relation counts have been checked.
