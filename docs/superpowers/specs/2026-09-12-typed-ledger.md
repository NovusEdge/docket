# Typed ledger and scoped context, version 0.8.0

## Purpose

Distinguish propositions, commitments, and unanswered questions. Give agents a
bounded briefing with relevant records and explicit support relationships. The
user approved breaking format changes and implementation on a separate branch.

## Record contract

The append-only JSONL file contains schema 2 records. Each record has `schema: 2`,
`kind`, `id`, `text`, `state`, `ts`, `author`, `session`, and `branch`.
IDs use c/d/q followed by a positive integer. Allocate the next global sequence
number across all kinds; `kind` remains authoritative and must match the prefix.

- Claim: a scoped proposition, represented by `text`. States: unassessed
  (default), accepted, disputed, rejected. Acceptance does not establish truth.
- Decision: a recorded scoped commitment to `choice`, selected
  from recorded `alternatives`, addressing `text`. States: adopted (default),
  revoked. A choice is required and included in alternatives automatically;
  recorded alternatives need not be exhaustive. `author` identifies the recorder,
  not the decision maker. Optional decision-only `decided_by` is a string naming
  the attributed decision maker, empty when unknown; it is self-reported metadata,
  not authenticated authority.
- Question: an unresolved inquiry in `text`. Its recorded state is always open.
  A current accepted claim or applicable adopted decision with an `answers` link resolves
  the target question in the derived view, without changing the original line.
  `resolved_by` exposes those answer IDs and effective state becomes resolved.
  A superseded or unavailable answer stops resolving it.

All records have these additional fields with empty defaults: `scope` (list of
path patterns or component names), `rationale` (string), `supports` (list of
nonempty conjunctive ID lists), `depends_on` (ID list), `answers` (ID list),
`supersedes` (ID list), `evidence` (list of objects containing a nonempty `ref`
and optional `checked_at` and `commit` strings), `revisit` and `cost_if_wrong`
(strings), and `pinned` (boolean). `choice` and `alternatives` are decision-only.

Relations refer to earlier existing records, never unknown IDs or self. Supports
may cite claims or decisions; alternatives are OR, members are AND. They record
declared grounds, not a verified logical implication. Only decisions may have
depends_on; targets may be claims or decisions. These are prerequisites, not
justification alternatives. Only claims and decisions may answer questions.
Supersession replaces the same kind and permanently retires the cited record;
reject attempts to supersede an already retired target so the successor is unique.
retiring the replacement does not revive its predecessor. Reject duplicate IDs,
invalid schema/shapes/states/relations clearly rather than silently losing data.
History and recorded state stay available; current/resolved views are derived.
No automatic truth propagation, dependent revocation, or transitive support-set
enumeration is introduced. Derive decision `applicable` and `blocked_by` from
depends_on: an accepted current claim is available; an adopted current decision
is available only if all its prerequisites are available. List unmet prerequisite
IDs including transitive blockers. A blocked decision keeps its recorded adopted
state but cannot resolve a question. Declared supports never change record state.

## CLI and module boundaries

Python remains stdlib-only, minimum 3.10. The checkout and plugins ship `lib/`
beside `bin/`; the executable resolves imports relative to its real file path.
Keep path/harness discovery in bin/docket. Core validation/storage/view helpers
live in lib/docket_ledger.py. Context selection/rendering lives in
lib/docket_context.py. Preserve the native installer and Go graph architecture.

Commands: `docket claim TEXT [--state accepted]`, `docket decision QUESTION
--choice VALUE [--alternative VALUE ...] [--decided-by ACTOR]`, `docket question TEXT`.
Shared options: --scope (repeat), --rationale, --supports (CSV; repeat for OR),
--depends-on (CSV), --answers (CSV), --supersedes (CSV), --evidence (repeat;
plain reference or JSON evidence object), --revisit, --cost, --pin. Keep list,
show, graph, context, where, init, completion. Remove old add/ruled-out/open
commands and because flag. List/graph support --kind and --state filters.
`show --json` returns the original record plus clearly named derived view data
if needed; never overwrite recorded state without exposing it. A --json list
form is useful for agents. Preserve plain/interactive graph and help behavior.

The core gives context and graph a projected list: same record fields, plus
`recorded_state`, effective `state`, `retired_by` (string), `resolved_by` (list),
and decision `applicable` (boolean) and `blocked_by` (ID list).
`lib/docket_context.py` exports:

    build_context(entries, *, query="", files=(), max_chars=8000,
                  ledger="", all_records=False) -> str

Entries are the complete projected history, in ledger order. Context filters
retired records unless reporting a cited historical premise. CLI flags are
--query, repeatable --file, --max-chars (minimum 512, default 8000), --all,
and existing --for harness envelopes. No provider tokenizer dependency; budgets
are explicitly characters, not tokens. No task query means a startup briefing.

## Context semantics

Include ledger identity and deterministic revision, distinguish commitments
from premises and questions, and explain how to retrieve full records. Rank
startup pins first; with a task query, matching records and their related records
take priority over unrelated pins. Use deterministic scope/path and text matches,
with stable ledger-order tie breaks and pins first among equally relevant entries.
Path scopes use slash-normalized repository-relative paths and fnmatch glob
patterns; literal directory scopes include descendants. Bare component names
match query text, without an implicit component-to-file mapping.
Include bounded related support/dependency/answer
records, preserving complete AND/OR formulas even when targets are omitted.
Do not equate retired records, non-accepted claims, revoked decisions, or blocked
decisions with available declared grounds. Show
explicit warnings and omitted counts, with a retrieval command. Do not claim
that references are freshly verified; print supplied evidence provenance and
revisit conditions. Keep entire record blocks, never truncate propositions or
negations to meet the budget. If even pinned records cannot fit, report omission.
Output must remain within max_chars including header/footer. Empty ledgers
produce no context. --all removes relevance filtering but still respects budget.
On compaction/resume rerun the current briefing through existing hook surfaces;
do not assume every harness implements the same lifecycle hooks. No embeddings,
external model calls, prompt-cache integration, or automatic configuration writes.

## Graph wire contract

Normalized graph JSON version 2 retains id/state/question/answer/cost/sets/supports/
retired_by keys for the renderer: question maps text, answer maps choice or
rationale, sets maps raw supports, supports is their deduplicated union. Add
kind, recorded_state, depends_on, answers, resolved_by, scope, rationale,
alternatives, evidence, revisit, author, ts, branch, session, pinned, decided_by,
applicable, blocked_by, supersedes. Overview
remains a first-support projection; details expose all relationship types with
distinct labels. Show kind and effective state, retirement, and full metadata.
Reject old wire version clearly. Preserve control-sequence sanitization, narrow
terminal behavior, search, colors, and terminal restoration.

## Migration and release

Normal reads reject schema 1 with actionable migration guidance. Provide a
standalone explicit migration tool under scripts/, requiring a classification
map for every old ID; do not guess kind from English prose. It writes a new
destination exclusively, leaves source intact, rewrites every relation through
the ID map, validates the result, and preserves source provenance and old text
in migration metadata when restructuring it. Cross-kind supersession or an
open-question resolution requires an explicit mapping treatment, not silent
edge loss. Tests cover refusals and relationship integrity. Migrate a copy of
our project ledger into the development worktree; leave main's active ledger
usable until the PR is merged. Keep the original copy and classification map.

The classification map is an object keyed by every original ID. Each value
requires kind, state, and text, plus choice for a decision; optional schema fields
and relation overrides use original IDs. Omitted supports translates because;
omitted supersedes translates the original supersession list. Explicit overrides,
including empty lists, are audited. Migrated records carry optional `legacy`:
an object with `source_id`, the complete source record in `raw`, and `relation_map`
containing original edges, rewritten edges, and the overridden relation names.
This metadata is historical data and grants no authority to the record.

Bump VERSION and both manifests to 0.8.0. Update public commands, formal
definitions, harness skill instructions, installation/migration guidance, and
CI to run all Python tests. After review and verification, merge the PR and
publish v0.8.0; the user explicitly authorized both during implementation.
No edits to installed plugin caches in this task.

## Acceptance

Exercise type/state/ref validation, append preservation, IDs, supersession and
question resolution, complete support alternatives, deterministic relevance and
budget limits, migration without overwriting, mixed-kind graph rendering, and
CLI integration from a symlink/outside the checkout. Run Python tests, Go tests
and vets, installer smoke coverage, then Sol review. Open a PR with breaking
changes and validation stated accurately; hosted CI must run on its exact head.
