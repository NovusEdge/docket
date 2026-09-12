# docket

**A decision ledger for coding agents.**

Keep track of what was decided, why, and what is still open. Docket gives agents
relevant context when a conversation resumes or gets compacted.

Records live in an append-only ledger. When a choice changes, the old reasoning
stays available.

## Install

Requires **Python 3.11+**, with no Python package dependencies.

```sh
curl -fsSLO https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py
python3 install.py
```

The installer guides you through setup and shows its plan before applying it.
It supports Claude Code, Codex, Gemini CLI, Cursor, GitHub Copilot CLI, and
OpenCode.

Start a new agent session after installation. Check the installed version with
`docket --version`.

[Installation, updates, and uninstall](docs/installation.md)

## Record claims, choices, and questions

| Record | What it captures | Example ID |
|---|---|---|
| **Claim** | A proposition to assess | `c1` |
| **Decision** | A choice and its reasoning | `d2` |
| **Question** | Something still unresolved | `q3` |

Record a claim:

```sh
docket claim "The service already runs Postgres in production"
```

Make a decision:

```sh
docket decision "Which database should we use?" \
  --choice "Postgres" \
  --rationale "Use the database we already operate"
```

Leave a question for later:

```sh
docket question "Which async driver should we use?"
```

Claims start as `unassessed`. Accepting a claim records a workflow assessment.
Verification of the claim and its evidence happens outside Docket.
You can also link records to evidence, prerequisites, answers, and earlier
choices they replace. See the [ledger reference](docs/ledger.md).

## Browse the ledger

```sh
docket graph
```

The installed native viewer gives you a selectable tree, search, and a detail
pane. Piped output stays plain text.

| Command | Use it to |
|---|---|
| `docket list` | List records |
| `docket show d2` | Inspect a record by its ID |
| `docket list --json` | Read structured records |
| `docket where` | Find the active ledger |
| `docket init` | Copy the ledger into `.docket/` for sharing in Git |

## Give an agent the context it needs

Configured session hooks load a briefing automatically. For a specific task,
select relevant records by topic and file:

```sh
docket context --query "database" --file src/db.py --max-chars 4000
```

Docket measures budget in **characters** instead of tokens. It keeps whole
records, reports what was omitted, and includes a command to retrieve more.

## Learn more

- [Installation](docs/installation.md): platforms, harness setup, updates, and graph controls.
- [Ledger reference](docs/ledger.md): states, dependencies, evidence, and scoped context.
- [Definitions](docs/definitions.md): what claims, decisions, and questions mean.
- [Decision chains](docs/decision-chains.md): the reasoning behind the model.
- [Agent context goals](docs/agent-context-goals.md): future directions for compact briefings, retrieval, and evaluation.

**Upgrading from before 0.8?** The ledger format and commands changed.
Follow the [migration guide](docs/ledger.md#explicit-migration-from-schema-1)
before using an existing ledger.
