# Quickstart

This page takes you from nothing to a working ledger in about five minutes. You
need Python 3.11 or later. Docket has no Python package dependencies.

## 1. Install

```sh
curl -fsSLO https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py
python3 install.py
```

The installer shows you its plan and waits for you to confirm it. It adds the
`docket` command to your `PATH` and sets up any agent tools it finds on your
machine.

Start a new agent session after the installer finishes. Then check that the
command works:

```sh
docket --version
```

The [installation page](installation.md) covers other install paths, updates,
and uninstall.

## 2. Create a ledger for your project

Go to your project and run:

```sh
cd ~/Projects/my-app
docket init
```

```
docket: created /home/you/Projects/my-app/.docket/ledger.jsonl
```

Your records now live in the repository, so your team shares them. Without
`docket init`, Docket keeps a private ledger in your home directory instead.
Run `docket where` any time you want to know which file is in use.

## 3. Record your first decision

A decision is a question plus the choice you made:

```sh
docket decision "Which database should the billing service use?" \
  --choice "Postgres" \
  --rationale "We already run Postgres, so we add no new operational burden" \
  --scope "billing/**"
```

```
d1  adopted  Which database should the billing service use?
```

Docket gives each record a short ID. You use that ID to link records together
later.

The `--scope` value matters more than it looks. Docket uses it to work out which
records matter for the files an agent is touching right now.

## 4. Leave a question for later

Not everything gets settled today. Record the open question so nobody has to
rediscover it:

```sh
docket question "Which async driver should the billing service use?" \
  --scope "billing/**"
```

```
q2  open  Which async driver should the billing service use?
```

## 5. Read it back

```sh
docket list
```

```
d1    adopted   Which database should the billing service use?
      Postgres
q2    open      Which async driver should the billing service use?
```

That is the whole loop. You record a choice when you make it, and Docket hands
it back when it becomes relevant again.

## What happens next

Your agent reads the ledger at the start of every session. It sees your
decisions, your premises, and your open questions, and it sees which ones apply
to the files in front of it. You do not have to explain the same choice twice.

Read [Recording](recording.md) next for the day to day habit, or
[Reading](reading.md) to see the other ways to get your records back.
