# Sharing and maintenance

Use this page to share a ledger, check a read error, or combine records from two
branches. For setup and updates, see [Installation](installation.md).

## Share a project ledger

From your project, run:

```sh
docket init
docket where
```

Docket creates a ledger at `.docket/ledger.jsonl` and copies any existing private
records for that project into it. Include `.docket/` in your normal Git commits
so other checkouts receive the same history.

Without a project ledger, Docket uses a private ledger under your home directory
for that project. `docket where` prints the active path.

## Check a ledger that will not read

```sh
docket check
```

A valid ledger reports its record count. An invalid ledger reports the faults it
can find, such as a repeated ID or a link to an unknown record.

Keep a copy of the file before attempting repairs. If it contains Git conflict
markers, recover the two branch versions before combining their records.

## Combine records from two branches

When both branches add records, they can allocate the same IDs. Combining the
lines directly does not resolve that conflict. Use `docket rebase` to give the
incoming records new IDs and update their links.

Start with two complete, valid ledger files:

- The active ledger contains the version you want to keep as the base.
- A separate file contains the other branch's version.

If Git has already inserted conflict markers, recover both versions first.
The [sharing reference](ledger.md#sharing-a-ledger) explains this requirement.

With the other version available in a separate checkout, preview the ID changes:

```sh
docket rebase ../other-branch/.docket/ledger.jsonl --dry-run
```

Check the map, then apply it and validate the result:

```sh
docket rebase ../other-branch/.docket/ledger.jsonl
docket check
```

Docket appends the other branch's records after the shared history and updates
links within the appended records. Commit the resulting ledger with your merge.

If both branches made different choices about the same issue, both choices
remain recorded. Decide which one to keep, then
[supersede the other](recording.md#change-an-earlier-choice).

If both branches superseded the same record, rebase stops for manual resolution.
An append failure can also leave part of the incoming history applied. Keep the
original files and inspect the report before retrying.

## Upgrade an old ledger

Ledgers from before 0.8 use an earlier format. Preview their conversion first:

```sh
docket migrate --dry-run
```

Read the proposed classifications and any warnings. If they need adjustment,
use the [migration reference](ledger.md#migrating-a-schema-1-ledger) to create
and edit a classification map.

When the conversion is right for your ledger:

```sh
docket migrate
docket check
```

Migration saves the original as `ledger.jsonl.schema1`. Running it on a current
ledger leaves the file unchanged.

## Adjust the briefing size

Try a different limit for one command before changing project settings:

```sh
docket context --query "billing" --max-chars 12000
```

For lasting changes, use a `config.toml` file beside the active ledger. In a
project ledger, that is `.docket/config.toml`.

The [configuration example](config.example.toml) lists the settings and defaults.
You can start with a small file containing only what you want to change:

```toml
[budget]
target = 12000
```

Docket reports an invalid setting instead of ignoring it. For selection weights,
index size, and budget behavior, see [Bounded context](ledger.md#bounded-context).

## Shell completion

Docket can print a completion script for your shell:

```sh
docket completion zsh
```

Use `bash` or `fish` instead of `zsh` for those shells. Save the output to the
completion location your shell uses.

## Update or remove Docket

Follow [Update, uninstall, and cleanup](installation.md#update-uninstall-and-cleanup).
Uninstall keeps your ledger files.
