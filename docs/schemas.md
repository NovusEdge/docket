# Schema versions

The ledger format carries a schema number on every line. This page lists the versions, what schema 3 changed, and how to upgrade a project and its branches.

## Versions

| Schema | Docket release | What it is |
| --- | --- | --- |
| 1 | before 0.8.0 | Untyped `dN` records with a `settled`, `ruled-out` or `open` state |
| 2 | 0.8.0 | Typed claims, decisions and questions with a kind and a state; the relations `supports`, `depends_on`, `answers` and `supersedes`; corrections and reviews; one id counter shared by every kind |
| 3 | 0.26.0 | Each kind numbered on its own |

Every command refuses a ledger older than the docket reading it, and `docket migrate` brings any older ledger to the current schema in one run.

## What changed in schema 3

| Field or file | Schema 3 |
| --- | --- |
| `schema` | 3 on every line, corrections and reviews included |
| Record ids | Count per kind (`c1`, `d1`, `q1`); a new record gets that kind's highest number plus one |
| `migrated_from` | Holds a migrated record's schema 2 id. Briefings never show it, and `list` and `show` JSON include it only with `--legacy`. Records created later never carry it |
| Correction and review ids | Follow their target: `d12.1` becomes `d5.1` |
| `legacy` | Left as it was |
| `.docket/features.jsonl` and its archive | Move to features schema 2, with the ledger ids they cite remapped |
| Feature keys | Ignore id tokens in a headline, so they survive the renumber |
| Merge and `docket rebase` | Require both sides at the same schema |

The migration rewrites every place a record names another by id: relations, correction and review targets, and id mentions in record prose. The prose fields are `text`, `choice`, `alternatives`, `rationale`, `cost_if_wrong` and `revisit`, a correction's fields and reason, and a review's note. Each mention is replaced once, so shifted ids never chain: `d4` becoming `d2` does not then become `d1`. A schema 1 record resolves its old ids through `legacy.source_id` first.

## Upgrading a project

1. Upgrade docket and the plugin. The session hook then shows the migrate instruction instead of a briefing.
2. Preview the migration.

   ```sh
   docket migrate --dry-run
   ```

   Read the prose changes and the unresolved tokens it lists. Note any change that rewrites an example id or an id quoted from another project.
3. Migrate. Add `--rewrite FILE...` for tracked, clean files that cite real ids of this ledger.

   ```sh
   docket migrate
   docket migrate --rewrite README.md docs/design.md
   ```

4. Fix the false positives you noted. Find each record with `docket list --where was:OLD` and change it with `docket correct`. When the false positive is in a decision's `choice`, restate the decision by supersession instead: the new docket cannot write to a schema 2 ledger, and `correct` cannot change `choice`.
5. Commit `ledger.jsonl` and the features files. Do not commit the `ledger.jsonl.schema2` backup.
6. Delete the backup once you have checked the result.

## Branches and collaborators

Each branch migrates itself before it merges. A merge across schemas leaves conflict markers and names the side that is behind. Abort the merge, rebase or cherry-pick in progress, migrate that branch, commit, and merge again.

Delete or move a backup left by another branch's migration before you migrate the next branch in the same worktree. Otherwise `docket migrate` refuses, because the backup differs from the ledger.

A collaborator on 0.25.x cannot read schema 3, so everyone upgrades first.

## If a migration is interrupted

Run it again. The migration replaces the features files and any named files before the ledger. It hard-links the original ledger to the backup and then replaces the ledger in one atomic step. A rerun therefore finishes the work, skips files already moved, and never maps an id twice.

A named file left half-done shows as modified. Restore it with `git checkout -- FILE` before you rerun.

## Finding an old id

```sh
docket list --where was:ID
```

This finds the record that carried an old id, retired records included. It matches `migrated_from`, or a schema 1 record's `legacy.source_id`.

`docket show ID` for an id that no longer exists points at that search. An old id that is also a current id resolves to the current record.
