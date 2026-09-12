# Typed ledger and scoped context, version 0.8.0

## Purpose

Distinguish propositions, commitments, and unanswered questions. Give agents a
bounded briefing with relevant records and explicit support relationships. The
user approved breaking format changes and implementation on a separate branch.

## Record contract

The append-only JSONL file contains schema 2 records. Every record has
`schema: 2`, `kind`, `id`, `text`, `state`, `ts`, `author`, `session`, and
`branch`.

IDs use `c`, `d`, or `q` followed by a positive integer. Allocate the next global
sequence number across all kinds. `kind` remains authoritative and must match
the prefix.

| Kind | Contract |
| --- | --- |
| Claim | A scoped proposition represented by `text`. States: `unassessed` (default), `accepted`, `disputed`, `rejected`. Acceptance does not establish truth. |
| Decision | A recorded scoped commitment to `choice`, selected from recorded `alternatives`, addressing `text`. States: `adopted` (default), `revoked`. A choice is required and is included in alternatives automatically; recorded alternatives need not be exhaustive. `author` identifies the recorder. Optional decision-only `decided_by` names the attributed decision maker, or is empty when unknown. This is self-reported metadata and does not authenticate authority. |
| Question | An unresolved inquiry in `text`. Its recorded state is always `open`. A current accepted claim or applicable adopted decision with an `answers` link resolves the target in the derived view. `resolved_by` exposes those answer IDs and effective state becomes `resolved`. A superseded or unavailable answer stops resolving it. |

All records have these additional fields with empty defaults:

- `scope`: list of path patterns or component names.
- `rationale`: string.
- `supports`: list of non-empty conjunctive ID lists.
- `depends_on`: ID list.
- `answers`: ID list.
- `supersedes`: ID list.
- `evidence`: objects containing a non-empty `ref` and optional `checked_at`
  and `commit` strings.
- `revisit` and `cost_if_wrong`: strings.
- `pinned`: boolean.

`choice` and `alternatives` are decision-only fields.

### Relationship and state rules

1. Relations refer to earlier existing records. They never refer to unknown IDs
   or to the record itself.
2. `supports` may cite claims or decisions. Alternatives are OR; members of one
   alternative are AND. These links record declared grounds and do not establish
   a verified logical implication.
3. Only decisions may have `depends_on`. Its targets may be claims or decisions.
   These links are prerequisites and are separate from justification
   alternatives.
4. Only claims and decisions may answer questions.
5. Supersession replaces the same kind and permanently retires the cited
   record. Reject attempts to supersede an already retired target so the
   successor remains unique. Retiring the replacement does not revive its
   predecessor.
6. Reject duplicate IDs and invalid schemas, shapes, states, or relations
   clearly rather than silently losing data.

History and recorded state stay available. Current and resolved views are
derived. The implementation introduces no automatic truth propagation,
dependent revocation, or transitive support-set enumeration. Derive decision
`applicable` and `blocked_by` from `depends_on`:

- An accepted current claim is available.
- An adopted current decision is available only when all its prerequisites are
  available.
- List unmet prerequisite IDs, including transitive blockers.
- A blocked decision keeps its recorded adopted state but cannot resolve a
  question.
- Declared supports never change record state.

## CLI and module boundaries

Python remains stdlib-only, with minimum version 3.10. The checkout and plugins
ship `lib/` beside `bin/`; the executable resolves imports relative to its real
file path.

| Responsibility | Module or boundary |
| --- | --- |
| Path and harness discovery | `bin/docket` |
| Core validation, storage, and view helpers | `lib/docket_ledger.py` |
| Context selection and rendering | `lib/docket_context.py` |
| Interactive graph | Existing native installer and Go graph architecture |

### Commands and options

```text
docket claim TEXT [--state accepted]
docket decision QUESTION --choice VALUE [--alternative VALUE ...] [--decided-by ACTOR]
docket question TEXT
```

Shared options are `--scope` (repeat), `--rationale`, `--supports` (CSV; repeat
for OR), `--depends-on` (CSV), `--answers` (CSV), `--supersedes` (CSV),
`--evidence` (repeat; plain reference or JSON evidence object), `--revisit`,
`--cost`, and `--pin`.

Keep `list`, `show`, `graph`, `context`, `where`, `init`, and `completion`.
Remove old `add`, `ruled-out`, and `open` commands and the `because` flag.
`list` and `graph` support `--kind` and `--state` filters.

`show --json` returns the original record and, when needed, clearly named derived
view data. It never overwrites recorded state without exposing it. A JSON form
of `list` is useful for agents. Preserve plain, interactive graph, and help
behavior.

### Projected records and context API

The core gives context and graph a projected list with the same record fields
plus `recorded_state`, effective `state`, `retired_by` (string), `resolved_by`
(list), and decision `applicable` (boolean) and `blocked_by` (ID list).

`lib/docket_context.py` exports:

```python
build_context(entries, *, query="", files=(), max_chars=8000,
              ledger="", all_records=False) -> str
```

Entries are the complete projected history in ledger order. Context filters
retired records unless reporting a cited historical premise. CLI flags are
`--query`, repeatable `--file`, `--max-chars` (minimum 512, default 8000),
`--all`, and existing `--for` harness envelopes. Provider tokenizers are not
used; budgets are explicitly characters. No task query produces a startup
briefing.

## Context semantics

The briefing must:

1. Include ledger identity and deterministic revision.
2. Distinguish commitments, premises, and questions.
3. Explain how to retrieve full records.
4. Rank startup pins first. With a task query, prioritize matching records and
   related records over unrelated pins.
5. Use deterministic scope/path and text matches, with stable ledger-order tie
   breaks and pins first among equally relevant entries.
6. Use slash-normalized repository-relative paths and `fnmatch` glob patterns
   for path scopes. Literal directory scopes include descendants. Bare component
   names match query text and do not imply a component-to-file mapping.
7. Include bounded related support, dependency, and answer records. Preserve
   complete AND/OR formulas even when targets are omitted.
8. Show explicit warnings and omitted counts with a retrieval command. Do not
   equate retired records, non-accepted claims, revoked decisions, or blocked
   decisions with available declared grounds.
9. Print supplied evidence provenance and revisit conditions. Do not claim that
   references were freshly verified.
10. Keep entire record blocks. Never truncate propositions or negations to meet
    the budget. If pinned records cannot fit, report the omission.

Output remains within `max_chars`, including header and footer. Empty ledgers
produce no context. `--all` removes relevance filtering while still respecting
the budget. On compaction or resume, rerun the current briefing through existing
hook surfaces because harness lifecycles can differ. Use no embeddings, external
model calls, prompt-cache integration, or automatic configuration writes.

## Graph wire contract

Normalized graph JSON uses version 2. Retain these renderer keys:

| Key | Meaning |
| --- | --- |
| `id`, `state`, `question`, `answer`, `cost` | Existing display fields. `question` maps `text`; `answer` maps `choice` or `rationale`. |
| `sets` | Raw `supports`; preserve its grouped structure. |
| `supports` | Deduplicated union of support IDs. |
| `retired_by` | Retirement relation. |

Add `kind`, `recorded_state`, `depends_on`, `answers`, `resolved_by`, `scope`,
`rationale`, `alternatives`, `evidence`, `revisit`, `author`, `ts`, `branch`,
`session`, `pinned`, `decided_by`, `applicable`, `blocked_by`, and `supersedes`.

The overview remains a first-support projection. Details expose all relation
types with distinct labels. Show kind, effective state, retirement, and complete
metadata. Reject old wire versions clearly. Preserve control-sequence
sanitization, narrow-terminal behavior, search, colors, and terminal restoration.

## Migration and release

Normal reads reject schema 1 with actionable migration guidance. Provide a
standalone explicit migration tool under `scripts/`. It must:

1. Require a classification map for every old ID. Do not guess kind from
   English prose.
2. Write a new destination exclusively and leave the source intact.
3. Rewrite every relation through the ID map.
4. Validate the result and preserve source provenance and old text in migration
   metadata when restructuring it.
5. Require explicit mapping treatment for cross-kind supersession or an
   open-question resolution. Do not silently drop edges.
6. Cover refusals and relationship integrity in tests.

Migrate a copy of the project ledger into the development worktree. Leave main's
active ledger usable until the PR is merged. Keep the original copy and
classification map.

The classification map is an object keyed by every original ID. Each value
requires `kind`, `state`, and `text`, plus `choice` for a decision. Optional
schema fields and relation overrides use original IDs. Omitted `supports`
translates `because`; omitted `supersedes` translates the original
supersession list. Explicit overrides, including empty lists, are audited.

Migrated records can carry optional `legacy` metadata:

```text
legacy:
  source_id: original ID
  raw: complete source record
  relation_map: original edges, rewritten edges, and overridden relation names
```

This metadata is historical data and grants no authority to the record.

Bump `VERSION` and both manifests to 0.8.0. Update public commands, formal
definitions, harness skill instructions, installation and migration guidance,
and CI to run all Python tests. After review and verification, merge the PR and
publish v0.8.0; the user explicitly authorized both during implementation. Make
no edits to installed plugin caches in this task.

## Acceptance

Exercise type/state/reference validation, append preservation, IDs, supersession
and question resolution, complete support alternatives, deterministic relevance
and budget limits, migration without overwriting, mixed-kind graph rendering,
and CLI integration from a symlink or outside the checkout.

Run Python tests, Go tests and vets, installer smoke coverage, and Sol review.
Open a PR with breaking changes and accurate validation. Hosted CI must run on
the exact PR head.
