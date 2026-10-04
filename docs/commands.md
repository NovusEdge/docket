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
| `docket export` | Write the relation graph as mermaid, graphviz DOT or Gephi CSV |
| `docket context` | Print the briefing an agent reads |
| `docket where` | Print which ledger file is in use |
| `docket check` | Report what makes the ledger unreadable |
| `docket feature ...` | Track a piece of work in flight; see below |
| `docket init` | Create a project ledger and copy any existing private records into it. It also adds the ledger merge driver to `.gitattributes` and, when `docket` is on PATH, registers it in the clone's git config; git invokes the driver during merges. Re-running it repairs a fresh clone |
| `docket migrate` | Convert a pre-0.8 ledger to the current schema |
| `docket rebase` | Renumber another branch's records onto this ledger |
| `docket update` | Update this Docket installation; `--check` reports without changing anything |
| `docket completion SHELL` | Print a shell completion script |

## Recording

`claim`, `decision`, and `question` share most of their flags.

| Flag | Applies to | Effect |
|---|---|---|
| `--choice C` | decision | The choice made. Required. |
| `--alternative A` | decision | An option considered but not chosen |
| `--decided-by WHO` | decision | Who made the decision |
| `--state S` | claim, decision | `unassessed`, `accepted`, `disputed`, `rejected` for a claim; `adopted` or `revoked` for a decision |
| `--scope GLOB` | all | Files the record applies to |
| `--rationale TEXT` | all | The reason for the claim, decision, or question |
| `--cost TEXT` | all | Consequences if the record is wrong |
| `--evidence REF` | all | A reference to evidence for the record |
| `--revisit TEXT` | all | A condition that calls for reviewing the record |
| `--supports IDS` | all | Earlier claims or decisions given as grounds |
| `--depends-on IDS` | decision | Claims or decisions required for this decision to apply |
| `--answers IDS` | claim, decision | Questions this record settles |
| `--supersedes IDS` | all | Same-kind records this one retires |
| `--supersede-reason R` | all | `restate`, `revise`, or `reverse`. Refused without `--supersedes`. Omitting it with `--supersedes` prints a hint and reads as `revise`. |
| `--pin` | all | Add a ranking bonus in briefings; inclusion is not guaranteed |

Every ID flag takes a comma-separated list. Repeat `--supports` for alternative
sets of grounds: `--supports c1,c2 --supports c3` means `(c1 AND c2) OR c3`.
Repeat `--scope`, `--evidence`, or `--alternative` for more than one value.

A prerequisite is followed through restatements and revisions to the head of
its chain. That head must be adopted and applicable for a decision, or accepted
for a claim. A reversal, or a rejected or revoked head, blocks. A decision with missing prerequisites
remains recorded as adopted but reports that it is blocked. See the
[relationship reference](ledger.md#relations).

`docket correct ID`

| Flag | Effect |
|---|---|
| `--text T`, `--rationale R` | Replace the record's text or rationale |
| `--scope PATH` | Replace the scope list. Repeat for more than one value. |
| `--evidence REF` | Replace the evidence list. Repeat for more than one value. |
| `--revisit R`, `--cost C` | Replace the revisit note or cost-if-wrong |
| `--pin`, `--unpin` | Replace the pinned flag |
| `--alternative A` | Decision only. Replace the alternatives list. Repeat for more. |
| `--decided-by WHO` | Decision only. Replace who made the call. |
| `--clear scope\|evidence\|alternatives` | Empty a list instead of replacing it. Repeat for more than one field. |
| `--supersede-reason R` | Relabel a supersession as `restate`, `revise`, or `reverse`. The record must have `supersedes`. |
| `--reason R` | Why the record was wrong |

Correct a record's wording or metadata. The record keeps its ID, and a
repeated flag replaces the whole list it names. The command refuses
`--choice`, `--state`, and the relation flags; supersede the record instead
to change those. `docket show ID` lists a record's corrections, and `docket
show ID.N` prints one correction with the values it replaced.

`docket review ID [--note TEXT]`

Record that you checked a claim or decision whose grounds changed. It appends a review line pinning each of the record's own revised, unassessed, disputed or circular grounds to that ground's current head. A flag inherited from a flagged or blocked ground is not pinned; it clears by reviewing or fixing that ground, so review the frontier first. The command refuses with "nothing to review" when no ground is owed, and with "its flags come from ..." when only inherited flags remain. A later revision of the same chain raises the flag again. See [review lines](ledger.md#review-lines).

## Reading

`docket list`

| Flag | Effect |
|---|---|
| `--kind K` | Only `claim`, `decision`, or `question` |
| `--state S` | Only records in that state |
| `--find TEXT` | Match record text or a decision's choice, ignoring case |
| `--where QUERY` | Filter with the [query language](#query-language); ANDs with the other flags |
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
| `--where QUERY` | Filter with the [query language](#query-language). In the viewer it is the initial filter, and clearing it shows every record. |
| `--interactive`, `--no-interactive` | Require or refuse the native viewer |
| `--plain`, `--pretty` | Force colour off or on |
| `--web` | Serve a live view to the browser on localhost until Ctrl-C. In a terminal it prints the URL; type `o` and Enter to open a browser, `q` and Enter to quit. With stdout piped it prints the bare URL and opens a browser itself. |
| `--port N` | Port for `--web`. Default 7347, or a free one if taken |

`docket export`

| Flag | Effect |
|---|---|
| `--format mermaid\|dot\|csv` | A mermaid flowchart, a graphviz digraph, or Gephi tables. Default `mermaid`. |
| `--kind`, `--state`, `--find`, `--where` | Filter, as in `list` |
| `--superseded` | Include retired records and the retire edges |
| `--out DIR` | Required by `--format csv`, which writes `nodes.csv` and `edges.csv` there |
| `--detail N` | Characters of text per node. Default 40, `0` for IDs alone. |
| `--direction LR\|TD\|RL\|BT` | With `mermaid` or `dot`, the layout direction. Default `LR`. |
| `--group none\|kind\|scope` | With `mermaid` or `dot`, draw boxes around records by kind or by shared scope directory. Default `none`. |
| `--focus ID` | Draw only the record and the records within `--hops` relation steps of it; a record with no relations draws alone. Exits 1 if `ID` is not in the selection. |
| `--hops N` | Steps from the focused record, 1 to 4. Default 2. Requires `--focus`. |

DOT output packs separate clusters into a grid and tags nodes and edges with `class` attributes.

Claims and decisions carry three derived fields in `--json` output and in `show`:

| Field | Meaning |
|---|---|
| `support` | `clean`, `flagged` (a ground changed or is unsettled and the record has not been reviewed against it), or `unsupported` (no complete set of grounds survives) |
| `review_owed` | a list of `{ground, head, because}`, one per ground to review; `docket review` clears them |
| `lost_grounds` | a list of `{ground, because}` for grounds an unsupported record lost |

`context` prints `review_owed:` and `lost:` lines under an affected record and ends with `# owe review: N; docket list --where is:flagged`. `context --since` adds ", N newly owe review" to its summary and counts a newly unsupported record as no longer available. `show` prints "Review owed" and "Lost grounds" sections, and the text `graph` marks records `? review` or `! lost`. `export` draws a flagged record with a dashed border and an unsupported one with a dotted border, and the csv node table carries a `support` column.

A decision's `depends_on` follows restatements and revisions to the head of the chain. A reversal, or a rejected or revoked head, blocks the decision; a revised prerequisite flags it. An unsupported prerequisite does not block.

### Query language

`--where` takes one query. The graph viewer's `/` input takes the same one.

    docket list --where 'kind:decision -is:retired scope:docket/ledger.py cache'

| Term | Matches when |
|---|---|
| `word` | the id, text, choice, or rationale contains it |
| `kind:K` | the kind is `claim`, `decision`, or `question` |
| `state:S` | the effective state is S; `state:resolved` finds answered questions |
| `scope:PATH` | a scope entry governs the file PATH, as `docket context --file` scores it |
| `scope:DIR/` | a scope entry starts with `DIR/`, or governs the directory |
| `is:pinned`, `is:corrected`, `is:retired`, `is:blocked` | the record is pinned, corrected, or retired, or is a blocked decision |
| `is:flagged`, `is:unsupported` | the record is a current accepted claim or adopted decision whose derived `support` is `flagged` or `unsupported` |
| `author:A`, `branch:B` | the author or the branch contains the value |
| `after:D`, `before:D` | the record's UTC date is on or after D, or before D; D is `YYYY-MM-DD` |

- Spaces separate terms. Double quotes hold spaces: `author:"a teammate"`.
- A quoted term is always text: `"d12:"` searches for the characters `d12:`.
- A leading `-` negates one term.
- Text terms AND each other, and `is:` terms AND each other. Repeats of any
  other field OR each other: `kind:claim kind:decision`. The groups AND.
- Case is ignored. An empty query matches everything.
- `scope:` takes a path, not a pattern. `scope:graph/**` asks which records
  govern a file named `graph/**`. Use `scope:graph/` for a directory.
- A retired record keeps its state, so `state:adopted` includes superseded
  decisions. `list` hides retired records unless you give `--superseded` or
  the query contains `is:retired`.
- A query that starts with `-` needs `=`: `--where=-kind:question`. argparse
  reads a separate `-kind:question` as an option.
- An export draws only records linked to another record in the selection. A
  narrow query can leave none, and the command then prints `no record in this
  selection carries a relation`.
- An unknown field or value, or a malformed date, exits 1 with a message that
  lists the valid values.

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

## Feature tracking

```
docket feature start <slug> --text TEXT --path GLOB [--path GLOB] [--intends TEXT]
docket feature list [--state STATE] [--json]
docket feature show <slug|id> [--json]
docket feature note <slug> TEXT
docket feature amend <slug> [--status STATUS] [--path GLOB] [--intends TEXT] [--include CSV] [--exclude CSV] [--clear FIELD]
docket feature done <slug> [--held CSV] [--failed CSV]
docket feature abandon <slug> --text REASON
docket feature brief [<slug|id>]
docket feature remap MAPFILE
docket feature gc [--expire DAYS]
```

`status` for `start` and `amend` is one of `active`, `paused`, `review`.
`done` and `abandon` close a feature and cannot be reopened under the same
ID; `start` a new one to resume the slug. `--include` and `--exclude` correct
which ledger records a feature's brief attaches, by ID. Each one replaces the
whole list, so `--clear include`, `--clear exclude` or `--clear intends`
empties a list that a later amend must not carry forward. `--held` and
`--failed` on `done` record a verdict on a claim the realized change set
touched; anything attached but unanswered comes back `unanswered`. `brief`
prints the ledger records governing a feature, strongest first; `remap`
repoints `include`/`exclude` lists through the ID map `docket rebase
--emit-map` writes. `gc` moves closed, unreferenced features into
`.docket/archive/`; `--expire DAYS` narrows which closed features qualify
and never triggers a move by itself. See [Feature tracking](features.md).

## Maintenance

`docket check` prints the record count when the ledger reads cleanly, and names
the bad line or relation when it does not.

`docket rebase OTHER` renumbers the records in `OTHER` onto the end of this
ledger. Use `--dry-run` to see the ID map first.

`docket migrate` converts a schema 1 ledger. Use `--dry-run` to review the
conversion, `--emit-map PATH` to write the derived classification map, and
`--map PATH` to apply a map you edited.

See [Maintenance](maintenance.md) for repair and migration procedures.

## Constructing

`docket construct PATHS` reads the markdown under `PATHS` and stages ledger
proposals in `.docket/proposed.jsonl`. It writes nothing to the ledger.
`--dry-run` lists the documents without API calls. `--jobs N` sets how many
documents are read at once.

`docket construct --review` prints the staged proposals with the source line
each one quotes.

`docket construct --accept` appends the proposals you marked `accepted`.
`--source PATH` takes one document's records and leaves the rest staged.

This command needs the `openai` SDK and an API key. See [Constructing on existing
projects](construct.md) and [Environment variables](environment.md).
