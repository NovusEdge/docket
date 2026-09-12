# Typed ledger implementation plan

> Historical plan for agentic workers. Use subagent-driven development;
> checkboxes track the recorded work status.

## Goal and architecture

**Goal:** Ship Docket 0.8.0 with typed records and bounded task context in a PR.

**Architecture:** Python stdlib modules own the schema and derived context. The
existing Go viewer consumes a version 2 projection. Migration is explicit.

**Tech stack:** Python 3.10+, existing Go/Charm modules, and no new
dependencies.

**Spec:** [Typed ledger and scoped context](../specs/2026-09-12-typed-ledger.md)

## Global constraints

- Preserve the source ledger and unrelated work. Work in
  `/tmp/docket-typed-ledger`.
- Keep legacy runtime compatibility and automatic truth propagation out of
  scope.
- Luna high implements. Sol reviews. The parent integrates and commits explicit
  paths.
- Use signed-off commits without em dashes, emojis, or `Co-Authored-By`
  trailers.

## Task 1: Typed storage and CLI (complete)

**Files:** `bin/docket`, `lib/docket_ledger.py`, `tests/test_docket.py`,
`tests/test_ledger.py`.

This task consumes the schema and context/graph interfaces in the spec. It
produces validated records and projected history for Tasks 2 and 3.

- [x] Add failing tests for mixed c/d/q IDs, invalid type/state/refs,
  supersession, answers, corrupt files, and old schema rejection.
- [x] Implement typed append/read/project helpers and new commands/options.
- [x] Adapt static graph/list/show/context dispatch and shell completions.
- [x] Preserve graph dispatch/terminal cleanup tests while replacing old
  fixtures.
- [x] Run `python3 tests/test_docket.py` and unittest discovery for new modules.

## Task 2: Bounded context (complete)

**Files:** `lib/docket_context.py`, `tests/test_context.py`.

This task consumes projected history and exports the exact `build_context`
signature in the spec.

- [x] Test pinned/task/path ranking, no-match behavior, complete formulas,
  retired/disputed premises, deterministic revision, Unicode budgets, and empty
  data.
- [x] Implement deterministic retrieval and whole-block rendering.
- [x] Compare full versus task briefing on a fixed mixed-topic fixture. Record
  sizes and relevant-decision coverage without treating this as a model-behavior
  measurement.
- [x] Run `python3 -m unittest discover -s tests -p test_context.py`.

## Task 3: Typed native graph (complete)

**Files:** `graph/main.go`, `graph/model.go`, `graph/main_test.go`.

The graph consumes wire version 2.

- [x] Add failing mixed-kind/state/detail/version tests.
- [x] Render all relation types and metadata without flattening support
  semantics.
- [x] Retain responsive layout, colors, sanitization, and interaction tests.
- [x] Run `go test ./...` and `go vet ./...` in `graph/`.

## Task 4: Migration, docs, and release integration (complete)

**Files:** `scripts/migrate_ledger.py`, `tests/test_migration.py`,
`docs/definitions.md`, `docs/decision-chains.md`, `docs/installation.md`,
`docs/ledger.md`, `README.md`, `skills/docket/SKILL.md`, `VERSION`, plugin
manifests, `justfile`, and CI workflows.

- [x] Require explicit classification and relationship mapping, reject
  overwrites, retain originals, and validate schema 2 output before creating the
  destination.
- [x] Classify the actual project ledger and migrate an isolated copy. Verify
  every source record and relation has a documented destination or explicit
  treatment.
- [x] Document formal types, commands, context limits, and migration examples.
- [x] Bump 0.8.0 and make local/CI test entry points include new tests.

## Task 5: Review and PR (in progress)

- [x] Sol reviews implementation against the spec and checks data-loss
  boundaries.
- [x] Resolve findings and run focused regression checks.
- [x] Run `just test`, both Go vets, CLI symlink checks, and mixed-ledger graph
  smoke checks.
- [ ] Commit signed-off changes, push an explicit branch refspec, open a PR, and
  inspect CI.
- [ ] Once review and CI pass, merge, publish v0.8.0, and verify release assets.
