# Recording

Docket stores three kinds of record. Picking the right one takes a second, and
it decides how later readers treat what you wrote.

| Kind | Use it for | Example |
|---|---|---|
| Claim | Something you believe about the world | "The service already runs Postgres" |
| Decision | A choice you committed to | "Use Postgres for billing" |
| Question | Something still unresolved | "Which async driver?" |

A claim is a premise. A decision is a commitment. A question is an invitation to
finish the thinking later. Your agent treats them differently, so the
distinction earns its keep.

## Record a decision

A decision needs the question it answers and the choice you made:

```sh
docket decision "Which database should the billing service use?" \
  --choice "Postgres" \
  --rationale "We already run Postgres, so we add no new operational burden" \
  --scope "billing/**"
```

Add `--alternative` for an option you looked at and put down. Add `--cost` to
say what it costs you if the choice turns out wrong:

```sh
docket decision "Where do we run the billing worker?" \
  --choice "The existing job runner" \
  --alternative "A dedicated Kubernetes deployment" \
  --cost "A move to Kubernetes means new deploy tooling and on-call runbooks" \
  --scope "billing/worker/**"
```

The cost field is the field people skip and later wish they had filled in. It
tells the next reader how much care the decision deserves.

## Record a claim

A claim is a statement you are relying on:

```sh
docket claim "The service already runs Postgres in production" \
  --state accepted \
  --evidence "terraform/db.tf names a managed Postgres instance" \
  --scope "db/**"
```

Claims start as `unassessed` unless you say otherwise. The four states are
`unassessed`, `accepted`, `disputed`, and `rejected`. Docket records the state
you chose. It does not check whether the claim is true, and your agent knows
that.

## Record a question

```sh
docket question "Which async driver should the billing service use?" \
  --scope "billing/**"
```

A question stays open until a decision answers it. You do not close it by hand.

## Link records together

Links are what turn a pile of notes into something an agent can reason over.

Point a decision at the claims it rests on with `--supports`:

```sh
docket decision "Which database should the billing service use?" \
  --choice "Postgres" --supports c1 --scope "billing/**"
```

Answer an open question with `--answers`:

```sh
docket decision "Which async driver should the billing service use?" \
  --choice "asyncpg" --answers q3 --scope "billing/**"
```

The question moves to `resolved` on its own once that decision exists.

Name a decision you must have in place first with `--depends-on`:

```sh
docket decision "Which connection pool size do we use?" \
  --choice "20 per worker" --depends-on d2 --scope "billing/**"
```

Only decisions take `--depends-on`. A claim or question with that flag is an
error, because a premise has no prerequisites.

Every link flag takes a comma separated list, so `--supports c1,c5` works.

## Change your mind

Docket never edits a line. You record the new version and point it at the old
one with `--supersedes`:

```sh
docket claim "The service already runs Postgres in production" \
  --state accepted --supersedes c1 \
  --evidence "terraform/db.tf names a managed Postgres instance"
```

The old record stays in the file with its original wording and state. It drops
out of `docket list` but you can still read it. That is the point of the ledger.
Six months later you can see what you believed, when you changed your mind, and
why.

Retire a decision the same way. Record the replacement with
`--supersedes d2`, or record it with `--state revoked` when you are dropping the
commitment and not replacing it.

## Useful extras

| Flag | What it does |
|---|---|
| `--scope` | Files or globs the record applies to, such as `billing/**` |
| `--evidence` | A pointer to what backs the record |
| `--rationale` | Why, in your own words |
| `--cost` | What it costs you if this is wrong |
| `--revisit` | A condition that should bring the record back up |
| `--decided-by` | Who made the call, on a decision |
| `--pin` | Keep the record in view even when it does not match the task |

Use `--pin` sparingly. A pinned record competes with the records that actually
match the task at hand.

## Where to go deeper

The [ledger reference](ledger.md) has the full field list, the state rules, and
the file format. [Definitions](definitions.md) has the formal vocabulary behind
these words.
