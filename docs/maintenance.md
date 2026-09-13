# Maintenance

Most weeks you never touch these commands. They matter on the day something goes
wrong, so it helps to know they exist.

## Find your ledger

```sh
docket where
```

```
/home/you/Projects/my-app/.docket/ledger.jsonl  (project, exists)
```

A project ledger lives in the repository and your team shares it. Without one,
Docket keeps a private ledger under your home directory and says `global`. Run
`docket init` to promote a project to its own shared ledger.

## When a ledger stops reading

```sh
docket check
```

A clean ledger reports its record count. A broken one names the line and the
fault. Reach for `check` first whenever a command fails or your session hook goes
quiet, because a normal read stops at the first fault and `check` reports all of
them.

## Two branches both recorded

This is the common one. Both branches appended records after the same last line,
so git reports a conflict on `ledger.jsonl`.

Do not resolve it by hand, and do not set a union merge driver on the file. Both
approaches leave two records holding one ID, and then every command fails
including the session hook.

Recover the other branch's file and run:

```sh
docket rebase ../other-branch/.docket/ledger.jsonl --dry-run
docket rebase ../other-branch/.docket/ledger.jsonl
```

Rebase finds the prefix both files share and appends the other side's remaining
records under fresh IDs. Links inside that tail follow the renumbering.
`--dry-run` prints the ID map and writes nothing, so run it first.

Docket does not merge the thinking for you. If both branches decided the same
question differently, you end up with two adopted decisions. Supersede one of
them and say why.

## Upgrading an old ledger

A ledger written before 0.8 uses the old schema. Commands fail with a message
pointing you here. Convert it in place:

```sh
docket migrate --dry-run
docket migrate
```

Migration keeps your original file at `ledger.jsonl.schema1`. A ledger already on
the current schema exits clean and changes nothing.

The conversion maps old states onto kinds and states, and prints a warning line
for each edge it repairs. Read the mapping table in the
[ledger reference](ledger.md#migrating-a-schema-1-ledger) before you run it on
history you care about.

## Tuning the briefing

Copy `docs/config.example.toml` from the repository to `.docket/config.toml` and
edit it. Every value is an integer, and every value in the example file is the
default, so you can delete the keys you do not want to change.

An unknown key is an error rather than a silent no-op. The briefing header names
your settings digest, so you can tell a tuned ledger from an untuned one at a
glance.

Raise `budget.target` if your agent keeps missing relevant records. Raise
`index.max_lines` if the briefing truncates a list of IDs you wanted.

## Shell completion

```sh
docket completion zsh
```

`bash`, `zsh`, and `fish` are supported. Send the output to the file your shell
loads completions from.

## Updating and removing Docket

Updates and uninstall live on the [installation page](installation.md#update-uninstall-and-cleanup).
Uninstall keeps every ledger.
