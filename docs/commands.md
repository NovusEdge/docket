# Command reference

Ledger commands use the file that `docket where` reports. Run
`docket COMMAND --help` for a command's flags. For a walkthrough, start with
[Your first decision](quickstart.md).

| Command | What it does |
|---|---|
| `docket claim TEXT` | Record a proposition |
| `docket decision QUESTION --choice C` | Record a commitment |
| `docket question TEXT` | Record an open question |
| `docket list` | List current records |
| `docket show ID` | Print one record in full |
| `docket graph` | Browse how records connect |
| `docket context` | Print the briefing an agent reads |
| `docket where` | Print which ledger file is in use |
| `docket check` | Report what makes the ledger unreadable |
| `docket init` | Create a project ledger and copy any existing private records into it |
| `docket migrate` | Convert a pre-0.8 ledger to the current schema |
| `docket rebase` | Renumber another branch's records onto this ledger |
| `docket completion SHELL` | Print a shell completion script |

## Recording

`claim`, `decision`, and `question` share most of their flags.

| Flag | Applies to | Effect |
|---|---|---|
| `--choice C` | decision | The choice made. Required. |
| `--alternative A` | decision | An option considered and put down |
| `--decided-by WHO` | decision | Who made the call |
| `--state S` | claim, decision | `unassessed`, `accepted`, `disputed`, `rejected` for a claim; `adopted` or `revoked` for a decision |
| `--scope GLOB` | all | Files the record applies to |
| `--rationale TEXT` | all | Why |
| `--cost TEXT` | all | What it costs you if this is wrong |
| `--evidence REF` | all | A pointer to what backs the record |
| `--revisit TEXT` | all | A condition that should bring this back up |
| `--supports IDS` | all | Earlier claims or decisions given as grounds |
| `--depends-on IDS` | decision | Claims or decisions required for this decision to apply |
| `--answers IDS` | claim, decision | Questions this record settles |
| `--supersedes IDS` | all | Same-kind records this one retires |
| `--pin` | all | Add a ranking bonus in briefings; inclusion is not guaranteed |

Every ID flag takes a comma-separated list. Repeat `--supports` for alternative
sets of grounds: `--supports c1,c2 --supports c3` means `(c1 AND c2) OR c3`.
Repeat `--scope`, `--evidence`, or `--alternative` for more than one value.

A decision prerequisite must be current, adopted, and applicable. A claim
prerequisite must be current and accepted. A decision with missing prerequisites
remains recorded as adopted but reports that it is blocked. See the
[relationship reference](ledger.md#relations).

## Reading

`docket list`

| Flag | Effect |
|---|---|
| `--kind K` | Only `claim`, `decision`, or `question` |
| `--state S` | Only records in that state |
| `--find TEXT` | Match record text or a decision's choice, ignoring case |
| `--superseded` | Include records a later one retired |
| `--oneline` | One line per record |
| `--json` | Print records as JSON |
| `--plain`, `--pretty` | Force colour off or on |

`docket show ID`

| Flag | Effect |
|---|---|
| `--json` | Print every field |
| `--at ID` | Show the record as history stood at that record |

`docket graph`

| Flag | Effect |
|---|---|
| `--style forest\|rail\|compact` | Static layout |
| `--kind`, `--state`, `--find` | Filter, as in `list` |
| `--interactive`, `--no-interactive` | Require or refuse the native viewer |
| `--plain`, `--pretty` | Force colour off or on |

`docket context`

| Flag | Effect |
|---|---|
| `--query TEXT` | Aim the briefing at a task |
| `--file PATH` | Aim it at a file. Repeat for more. |
| `--max-chars N` | Set a hard character ceiling. The default minimum is 512. |
| `--all` | Drop relevance filtering, keep the budget |
| `--auto-scope`, `--no-auto-scope` | Derive scope from the working tree, or never |
| `--since ID` | Report changes after that record; also accepts `ID@DIGEST` from a briefing |
| `--for gemini\|copilot\|cursor` | Wrap the output in that tool's hook format |

## Maintenance

`docket check` prints the record count when the ledger reads cleanly, and names
the bad line or relation when it does not.

`docket rebase OTHER` renumbers the records in `OTHER` onto the end of this
ledger. Use `--dry-run` to see the ID map first.

`docket migrate` converts a schema 1 ledger. Use `--dry-run` to review the
conversion, `--emit-map PATH` to write the derived classification map, and
`--map PATH` to apply a map you edited.

See [Maintenance](maintenance.md) for when to reach for these.
