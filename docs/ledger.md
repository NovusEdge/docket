# Ledger reference

Docket 0.8.0 writes schema 2 records as append-only JSONL. Each non-empty line
is one JSON object. Reads validate the complete file, so an invalid line or
relation is reported instead of being silently dropped.

## Record types

Every record has `schema`, `kind`, `id`, `text`, `state`, `ts`, `author`,
`session`, and `branch`.

| Kind | Meaning | Recorded state | Type-specific fields |
|---|---|---|---|
| `claim` | A scoped proposition | `unassessed`, `accepted`, `disputed`, `rejected` | none |
| `decision` | A commitment to a choice | `adopted`, `revoked` | `choice`, `alternatives`, optional `decided_by` |
| `question` | An unanswered inquiry | `open` | none |

IDs use the type prefix and a positive global sequence number: `c1`, `d2`, and
`q3`. The sequence is shared across kinds. A question's recorded state remains
`open`; a current accepted claim or applicable adopted decision that links to it
through `answers` gives it effective state `resolved` in a derived view.

Recorded state is what the append-only line says. Effective state includes
derived question resolution and decision applicability. Currentness is separate
from both: a record is historical when a later same-kind record supersedes it.
The original line, state, and provenance remain available. A superseded record
is not current support.

Acceptance and adoption are workflow statuses. They do not establish that a
claim is true or that a decision is correct. Evidence is supplied provenance,
not a freshness or truth guarantee.

## Common fields

The following fields have empty defaults: `scope` (path patterns or component
names), `rationale`, `supports`, `depends_on`, `answers`, `supersedes`,
`evidence`, `revisit`, `cost_if_wrong`, and `pinned` (false).

Path scopes are normalized repository-relative paths. Scopes containing a slash
or glob metacharacters use `fnmatch`; a literal directory scope also matches its
descendants. A bare component name matches query text only, without an implicit
component-to-file mapping.

`evidence` is a list of objects. Each object needs a non-empty `ref` and may
include `checked_at` and `commit` strings. `author` identifies the recorder.
For decisions, `decided_by` optionally attributes the commitment to another
person or agent. Both values are self-reported metadata, not authentication.

`supports` is a list of non-empty ID lists. IDs in one inner list are conjunctive
AND requirements. Inner lists are alternative OR sets:

```json
"supports": [["c1", "c2"], ["c3"]]
```

This means `(c1 AND c2) OR c3`. These are declared grounds, not verified
logical implications. Only claims and decisions can be support targets.

`depends_on` is a separate operational relation for decisions. Its targets are
claims or decisions and it has no OR interpretation. An adopted decision is
applicable when its claim prerequisites are accepted and current and its
decision prerequisites are adopted, current, and applicable. Otherwise a
projected record contains `applicable: false` and `blocked_by` with unavailable
prerequisites. The recorded choice remains adopted, but a blocked decision does
not resolve a question.

`answers` is a question-resolution link. Only claims and decisions can answer a
question. A current accepted claim or applicable adopted decision resolves its
target in the projected view. `supersedes` retires same-kind records. Docket
rejects self-links, unknown or later IDs, cross-kind supersession, and
supersession of an already retired record.

## Derived views

The validator preserves the original record. `project` adds `recorded_state`,
effective `state` for resolved questions, `retired_by`, and `resolved_by`. It
also adds `applicable` and `blocked_by` to decisions. Retiring a record does not
rewrite its state, revoke dependent decisions, or revive an older predecessor.

`show --json` exposes the original record and derived fields. `list --json`
returns machine-readable projected records. `graph` sends a version 2 projection
to the native viewer. The graph projection keeps the legacy renderer keys
`question`, `answer`, `cost`, `sets`, and the deduplicated `supports` union while
adding the typed metadata and relation fields. `sets` preserves the complete
AND/OR formula; the union is only a renderer convenience.

## Bounded context

`docket context` renders projected records for a harness. Its default budget is
8,000 characters and the minimum accepted budget is 512. The budget counts the
header, complete record blocks, warnings, and retrieval footer. Docket never
cuts a proposition or negation in half to meet it.

With no task query or file scope, startup context ranks pinned records first. A
task query or `--file` scope ranks matching text and paths before unrelated pins,
then adds bounded directly related records in both directions: grounds,
prerequisites, dependents, questions, and their answers. At most 64 related
records are admitted, and only after their selected record fits. Pins break
ties between equally relevant records. `--all`
removes relevance filtering but keeps the budget. The header includes ledger
identity and a deterministic revision. Omitted and unrelated counts, incomplete
relation coverage, evidence-provenance limits, and a `docket show ID --json`
retrieval command are explicit in the footer.

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
operation and never overwrites the source or an existing destination. It
requires one JSON classification map entry for every source ID. The map must
choose `kind`, `state`, and `text`; Docket does not infer a type from English
prose.

For a source ledger at `old/ledger.jsonl`, create `map.json` with entries such as:

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

Run the standalone tool with a new destination:

```sh
python3 scripts/migrate_ledger.py old/ledger.jsonl \
  --map map.json \
  --output .docket/ledger-v2.jsonl
```

The tool validates every source relation and every mapped record before opening
the destination with exclusive-create semantics. It rewrites relation IDs
through the map, retains the source text and relation treatment in `legacy`
metadata, and leaves the source intact. A source `because` list maps to
`supports` unless an explicit override is supplied. Cross-kind supersession or
an old line that needs to become a question answer requires explicit relation
overrides; the tool refuses silent edge loss. A question mapping uses recorded
state `open`, even when later answer links make its derived state `resolved`.

Keep the original ledger and classification map with the migration review.
Switch the active project ledger only after the destination has passed the
validator and its record and relation counts have been checked.
