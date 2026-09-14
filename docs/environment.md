# Environment variables

Docket reads its configuration from a `docket.toml` beside your ledger. The
variables here cover the things a config file cannot answer: where the ledger
lives before one is found, who is writing, and which service `docket construct`
calls.

Nothing on this page is required. Docket runs with none of it set.

## Where the ledger lives

| Variable | Effect |
|---|---|
| `DOCKET_HOME` | The global ledger store. Overrides every other location. |
| `CLAUDE_CONFIG_DIR` | Used when `DOCKET_HOME` is unset. The store becomes `$CLAUDE_CONFIG_DIR/docket`. |

Without either, the store is `~/.claude/docket`.

A project with a `.docket/ledger.jsonl` uses that file, and none of these
variables apply. The global store holds ledgers for projects that have not
committed one. Run `docket where` to see which file is in use.

`CLAUDE_CONFIG_DIR` exists so an isolated Claude profile keeps its own ledgers
instead of sharing yours.

## Who recorded the entry

Every record names its author, because two agents sharing one ledger is the
normal case and an entry that does not say who wrote it cannot be weighed.

| Variable | Effect |
|---|---|
| `DOCKET_AUTHOR` | The author name. Checked first. |
| `AI_AGENT` | Used when `DOCKET_AUTHOR` is unset. The part before the first `_` becomes the author. |
| `CODEX_SANDBOX`, `CODEX_HOME` | Either one present records `codex`. |
| `USER` | The last fallback. |

If none resolves, Docket records `unknown` and prints a warning naming
`DOCKET_AUTHOR`. A blank author cannot be told from a missing one once written.

The session ID comes from `CLAUDE_SESSION_ID`, `CLAUDE_CODE_BRIDGE_SESSION_ID`
or `SESSION_ID`, in that order. Claude Code has used more than one name across
versions.

## `docket construct`

These apply to `docket construct` alone. See [Constructing on existing projects](construct.md).

| Variable | Effect |
|---|---|
| `OPENROUTER_API_KEY` | Calls OpenRouter. One key reaches every provider through one endpoint. |
| `GEMINI_API_KEY` | Used when `OPENROUTER_API_KEY` is unset. Calls Gemini's OpenAI-compatible endpoint. |
| `DOCKET_CONSTRUCT_MODEL` | The model. Defaults to `google/gemini-3.8-flash` on OpenRouter and `gemini-3.8-flash` on Gemini. |
| `DOCKET_CONSTRUCT_BASE_URL` | The endpoint, for a gateway that speaks the same protocol. |

Construct refuses to run with neither key set, and names both in the message.

A Gemini key beginning `AQ.` works. It authenticates with the `x-goog-api-key`
header and as a bearer token on the OpenAI-compatible endpoint.

## Update checks

Docket checks for a newer release once a day, in a detached background process,
and prints a notice above the context briefing.

| Variable | Effect |
|---|---|
| `DOCKET_NO_UPDATE_CHECK` | Any value except empty or `0` disables the check and the notice. |
| `XDG_STATE_HOME` | Where the check records when it last ran. Defaults to `~/.local/state`. |

## Terminal output

| Variable | Effect |
|---|---|
| `NO_COLOR` | Any value disables colour. |
| `WT_SESSION` | On Windows, colour is off unless this is set. |

Colour is also off when output is not a terminal, and when any of
`CLAUDE_SESSION_ID`, `CLAUDE_CODE_BRIDGE_SESSION_ID`, `SESSION_ID`, `AI_AGENT`,
`CODEX_SANDBOX` or `CODEX_HOME` is set. Several agent harnesses run shell
commands over a pseudo-terminal, so a terminal check alone reads them as a
person. Escape codes in a model's context window cost more than a missing
colour, so the doubt resolves towards plain.

Pass `--pretty` to force colour on and `--plain` to force it off.

## Installing

| Variable | Effect |
|---|---|
| `DOCKET_INSTALLER_VERSION` | Installs a named release tag instead of the latest. Must be a simple tag. |

See [Installer options and behavior](installer-reference.md).

## Running the tests

| Variable | Effect |
|---|---|
| `DOCKET_CORPUS` | A checkout holding `context/**/*.md`, for the construct corpus tests. They skip without it. |
