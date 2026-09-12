# Typed Ledger Implementation Plan

> **For agentic workers:** Use subagent-driven-development. Checkboxes track work.

**Goal:** Ship Docket 0.8.0 with typed records and bounded task context in a PR.

**Architecture:** Python stdlib modules own the schema and derived context.
The existing Go viewer consumes a version 2 projection. Migration is explicit.

**Tech Stack:** Python 3.10+, existing Go/Charm modules; no new dependencies.

**Spec:** ../specs/2026-09-12-typed-ledger.md

## Global Constraints

- Preserve the source ledger and unrelated work; work in /tmp/docket-typed-ledger.
- No legacy runtime compatibility or automatic truth propagation.
- Luna high implements; Sol reviews. Parent integrates and commits explicit paths.
- No em dashes, emojis, or Co-Authored-By trailers; signed-off commits.

## Task 1: Typed storage and CLI (in progress)

Files: bin/docket, lib/docket_ledger.py, tests/test_docket.py, tests/test_ledger.py.
Consumes the schema and context/graph interfaces in the spec. Produces validated
records and projected history for Tasks 2 and 3.

- [ ] Add failing tests for mixed c/d/q IDs, invalid type/state/refs, supersession,
  answers, corrupt files, and old schema rejection.
- [ ] Implement typed append/read/project helpers and new commands/options.
- [ ] Adapt static graph/list/show/context dispatch and shell completions.
- [ ] Preserve graph dispatch/terminal cleanup tests while replacing old fixtures.
- [ ] Run `python3 tests/test_docket.py` and unittest discovery for new modules.

## Task 2: Bounded context (pending; independent implementation)

Files: lib/docket_context.py, tests/test_context.py. Consumes projected history;
exports the exact build_context signature in the spec.

- [ ] Test pinned/task/path ranking, no-match behavior, complete formulas,
  retired/disputed premises, deterministic revision, Unicode budgets, and empty data.
- [ ] Implement deterministic retrieval and whole-block rendering.
- [ ] Compare full vs task briefing on a fixed mixed-topic fixture; record sizes
  and relevant-decision coverage without pretending this measures model behavior.
- [ ] Run `python3 -m unittest discover -s tests -p test_context.py`.

## Task 3: Typed native graph (pending; independent implementation)

Files: graph/main.go, graph/model.go, graph/main_test.go. Consumes wire version 2.

- [ ] Add failing mixed-kind/state/detail/version tests.
- [ ] Render all relation types and metadata without flattening support semantics.
- [ ] Retain responsive layout, colors, sanitization, and interaction tests.
- [ ] Run `go test ./...` and `go vet ./...` in graph/.

## Task 4: Migration, docs, and release integration (pending)

Files: scripts/migrate_ledger.py, tests/test_migration.py, docs/definitions.md,
docs/decision-chains.md, docs/installation.md, docs/ledger.md, README.md,
skills/docket/SKILL.md, VERSION, plugin manifests, justfile, CI workflows.

- [ ] Require explicit classification and relationship mapping, reject overwrites,
  retain originals, and validate schema 2 output before creating destination.
- [ ] Classify the actual project ledger and migrate an isolated copy; verify every
  source record and relation has a documented destination or explicit treatment.
- [ ] Document formal types, commands, context limits, and migration examples.
- [ ] Bump 0.8.0 and make local/CI test entry points include new tests.

## Task 5: Review and PR (pending)

- [ ] Sol reviews implementation against spec and checks data-loss boundaries.
- [ ] Resolve findings and run focused regression checks.
- [ ] Run `just test`, both Go vets, CLI symlink and mixed-ledger graph smoke checks.
- [ ] Commit signed-off changes, push explicit branch refspec, open PR, inspect CI.
- [ ] Once review and CI pass, merge, publish v0.8.0, and verify release assets.
