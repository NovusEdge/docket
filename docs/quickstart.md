# Your first decision

Create a project ledger, record a choice, and read it back. If Docket is not
installed yet, follow [Installation](installation.md) first.

The commands below use a terminal. You can also ask your agent to carry out the
same steps.

## 1. Open your project

In your terminal, go to the project where you want to keep decisions. Replace
this example path with your own:

```sh
cd ~/Projects/my-app
docket init
```

Docket creates `.docket/ledger.jsonl` in your repository. If you already have a
private ledger for this project, it copies those records into the new file.

Run this to confirm which ledger is active:

```sh
docket where
```

The output should name the `.docket/ledger.jsonl` file in your project. To share
it with your team, include `.docket/` in a Git commit.

## 2. Record a choice

For this example, imagine you are adding billing to an existing service:

```sh
docket decision "Which database should billing use?" \
  --choice "Postgres" \
  --rationale "We already run Postgres for the rest of the service" \
  --scope "billing/**"
```

In an empty ledger, Docket replies:

```text
d1  adopted  Which database should billing use?
```

`d1` is the record's ID. Your ID may be different if the ledger already has
records. `adopted` means this is a choice you have committed to.

The scope `billing/**` connects the decision to files under `billing/`. It helps
Docket find the decision when you or your agent work on that part of the project.

## 3. Leave a question for later

```sh
docket question "Which database driver should billing use?" \
  --scope "billing/**"
```

In the same fresh ledger, this creates `q2`. The question stays open until you
link a suitable answer to it.

## 4. Read your records

```sh
docket list
```

You will see the adopted decision and the open question. To read the decision
in full, use the ID printed when you recorded it:

```sh
docket show d1
```

You can also open `docket graph` to browse the ledger in the terminal viewer.

## 5. Bring the choice into your next task

```sh
docket context --query "billing" --file billing/db.py
```

This prints a briefing for the task. With these two records, it includes your
database choice and the question you still need to answer.

If you configured an agent during installation, start a new session in this
project. Ask it to read the Docket context and tell you what is still open.

Continue with [Recording decisions](recording.md) to learn how to answer the
question or replace an earlier choice. [Working with your agent](agents.md)
shows how to use the same workflow in a conversation.
