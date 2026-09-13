# Recording decisions

Record a choice when you make it, while the reason is still clear. Add a claim
when a statement matters to later work, or a question when you need to leave
something open.

You do not need to record every step of a conversation. Keep the things another
person or agent would need to understand before continuing the work.

## Choose a record type

| Use a… | When you want to say… |
|---|---|
| **Claim** | “This is a statement we should assess or check again later.” |
| **Decision** | “This is the choice we are committing to, and here is why.” |
| **Question** | “We still need an answer to this.” |

The examples below form one small ledger. They assume you start with no records.
If you use an existing ledger, substitute the IDs printed by your commands.

## Save a statement you are relying on

Suppose you have checked the service configuration and confirmed that it uses
Postgres:

```sh
docket claim "The service already runs Postgres" \
  --state accepted \
  --evidence "terraform/db.tf" \
  --scope "billing/**"
```

This creates `c1`. The evidence field points a later reader to the file you
checked.

Without `--state accepted`, a claim starts as `unassessed`. You can also record
it as `disputed` or `rejected`. Docket stores your assessment; it does not check
the evidence for you.

## Record the choice and its reason

```sh
docket decision "Which database should billing use?" \
  --choice "Postgres" \
  --rationale "Use the database we already operate" \
  --supports c1 \
  --scope "billing/**"
```

This creates `d2`. The `--supports c1` link lets a reader follow the choice back
to the claim behind it. You can record a decision without a support link when
there is no earlier record to cite.

For a choice that deserves more explanation, add `--alternative` for another
option you considered or `--cost` for what would happen if the choice were wrong.
Use `--decided-by` when you are recording a choice that someone else made.

## Leave a question, then answer it

First, record the open question:

```sh
docket question "Which database driver should billing use?" \
  --scope "billing/**"
```

This creates `q3`. Later, link your choice to it:

```sh
docket decision "Which database driver should billing use?" \
  --choice "psycopg" \
  --rationale "Use the driver already configured in the service" \
  --answers q3 \
  --scope "billing/**"
```

This creates `d4`, and `q3` now appears as `resolved`. A current accepted claim
can also answer a question, which is useful when you needed a fact rather than
a choice.

An answer must still be current to resolve the question. A decision must also
be adopted and have any required prerequisites available. The
[relationship rules](ledger.md#answers-and-supersession) explain the details.

## Change an earlier choice

Add a new decision that names the one it replaces:

```sh
docket decision "Which database driver should billing use?" \
  --choice "asyncpg" \
  --rationale "The billing worker now uses an async database interface" \
  --supersedes d4 \
  --answers q3 \
  --scope "billing/**"
```

This creates `d5`. The old decision disappears from the default list, but
`docket show d4` still shows it. The `--answers q3` link keeps the original
question answered by your new choice.

If you drop a commitment without choosing a replacement, record a revoked
decision that supersedes it:

```sh
docket decision "Which database driver should billing use?" \
  --choice "asyncpg" \
  --state revoked \
  --supersedes d5 \
  --rationale "Billing is moving out of this service" \
  --scope "billing/**"
```

The previous commitment is now retired. With no current answer left, `q3`
appears as open again.

Use the same approach to revise a claim: write its new assessment and add
`--supersedes` with the old claim's ID. A replacement must have the same record
type as the record it retires.

## Make records easier to find

Use `--scope` for a path or pattern such as `billing/**`. Repeat it if a record
applies to several parts of the project.

Write enough in `--rationale` for someone to understand the choice without the
original conversation. Add `--revisit` when there is a clear reason to check it
again, such as a dependency upgrade.

`--pin` gives a record more weight in briefings. It does not guarantee inclusion,
so a useful scope is still worth adding.

For operational prerequisites, use `--depends-on` on a decision. These are
different from the reasons recorded through `--supports`. See
[Decision prerequisites](ledger.md#decision-prerequisites) when you need them.

Next, use [Reading your ledger](reading.md) to find records and follow their
history. The [command reference](commands.md#recording) lists the recording flags.
