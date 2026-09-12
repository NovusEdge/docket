# Installation

Docket 0.8.0's schema 2 ledger CLI requires Python 3.10 or later. It has no
Python package dependencies. The 0.8.0 CLI uses `claim`, `decision`, and
`question` records. The pre-0.8 `add`, `open`, `ruled-out`, `--answer`, and
`--because` interface is removed. Read [the ledger reference](ledger.md) before
migrating a schema 1 ledger.

An agent harness needs two integrations:

1. A session-start hook runs `docket context` and adds its output to the model context.
2. An instruction document tells the model when to record a decision.

All integrations use the same ledger. A project can therefore use more than one
agent harness.

After installation, verify the command and inspect the active ledger:

```sh
docket --version
docket where
```

The session-start hook runs `docket context`. With a task query, a harness may
pass `--query`, repeat `--file`, and set `--max-chars`; without a query, the
briefing is startup context. The budget is in characters and has a minimum of
512. `--all` removes relevance filtering while keeping the budget.

## The installer

```sh
curl -fsSLO https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py
python3 install.py
```

`curl -O` saves the file as `install.py` in the current directory. Outside a
checkout, this compatibility launcher downloads a native installer and verifies
it against the release's `SHA256SUMS` file before running it. The release
recipes build Linux, macOS, and Windows assets for amd64 and arm64; a matching
published asset must exist for the launcher to use it. Set
`DOCKET_INSTALLER_VERSION` to select a published release tag.

From a checkout, run `python3 installer/install.py`. This builds the native
installer locally with Go 1.26 or later and runs it against that checkout. To
build it without running it, use `just installer-build`. The Go module,
installer code, and installer tests live in `installer/`.

The installer clones the repository when you do not run it from a checkout. It
adds the command to `PATH`, and by default configures Claude Code plus any other
harnesses it detects.

Installing or re-running the normal managed flow clones into a temporary
directory and swaps the result into place. It preserves a `.docket` ledger
inside the managed checkout; other local changes in that checkout are replaced.
An unrelated nonempty directory is rejected. Running from an existing source
checkout installs that checkout without replacing it.

The native installer uses Bubble Tea, Bubbles, and Lip Gloss for its guided
flow and prepares the native `docket-graph` viewer. It builds the viewer from
the checkout when Go is available. Without Go, it fetches the matching viewer
asset and verifies `GRAPH-SHA256SUMS`; this requires that the asset has been
published for the checked-out version. The repository contains release recipes
for these assets, but building them does not publish a release.

In a terminal, and without `--yes`, `--no-tty`, `--dry-run`, or `--harness`,
the installer runs a guided flow instead of taking every default silently.

The installer runs inline on an interactive terminal and leaves the result in
scrollback. Unattended runs use plain output. The launcher creates no Python
environment and installs no Python packages.

The guided flow asks for:

1. Where to put the `docket` command and, for a downloaded installer, its checkout.
2. Which harnesses to configure, each with its detection result. Detected
   ones start selected. An undetected harness can still be selected, for a
   tool you are about to install.
3. If the chosen location is not already on `PATH`, it shows the exact line
   and file and asks before appending.
4. The full plan, including checkout updates and external commands, before applying it.

Cancelling before confirmation leaves the installation unchanged. Cancelling
during installation stops further actions; completed actions remain applied.

| Option | Effect |
|---|---|
| `--dry-run` | Print every planned operation without applying it |
| `--harness NAME` | Configure one harness; repeat for more; skips the guided flow |
| `--project` | Put the Claude skill and Cursor rule in this repository; hook configs keep user scope |
| `--prefix DIR` | Put the command in `DIR` |
| `--dir DIR` | Put the managed checkout in `DIR` |
| `--checkout DIR` | Use an existing source checkout without replacing it |
| `--yes` | Take every default and do not prompt |
| `--no-tty` | Treat stdin as non-interactive, same effect as `--yes` on prompting |
| `--update` | Refresh the existing Docket checkout and native graph viewer; keep harness and PATH configuration unchanged |
| `--uninstall` | Remove what the installer wrote |
| `--version` | Print the installer version |

`--yes` and non-interactive runs apply defaults, including a needed PATH change.
Use `--dry-run` to inspect those changes first. `just verify` tests installation
and removal in a temporary home.

The uninstall keeps every ledger.

After installation, `docket`, `docket -h`, and `docket --help` print the version
and full top-level command help. Use `docket --version` for the concise version
only.

For a managed install, run the downloaded launcher with `--update` to
fast-forward the managed checkout and refresh its viewer. The command must
already be installed; this mode does not add PATH entries or change harness
configuration. Add `--dry-run` to review the checkout and viewer operations
first. It cannot be combined with `--harness`, `--project`, or `--uninstall`.

From a source checkout, `python3 installer/install.py --update` uses that
checkout and does not fetch Git. It refreshes the viewer when Go is available.
`just update` runs this source-checkout path. An explicit `--checkout DIR` also
uses that source tree without replacing it.

`just clean` removes repository build outputs, release outputs, and Python
caches. It preserves source files, `.docket` ledgers, configuration, and shared
Go caches.

Installing a Claude or Codex plugin from this repository does not download a
compiled viewer. For a source checkout with Go installed, run `just graph-build`,
or run the installer against that checkout. If no viewer is available,
`docket graph` uses its compact text fallback in automatic terminal mode and
prints installation guidance. It does not access the network or invoke Go while
displaying a graph.

## Manual installation

Clone the repository:

```sh
git clone https://github.com/NovusEdge/docket.git ~/Projects/docket
```

Add the command to `PATH` if you want to use it in a shell:

```sh
mkdir -p ~/.local/bin
ln -s ~/Projects/docket/bin/docket ~/.local/bin/docket
```

To enable the interactive graph viewer in a source checkout, install Go 1.26
or later and run:

```sh
just graph-build
```

The viewer is written to `graph/docket-graph`. Plugin files alone do not
include this compiled executable.

## Browse the decision graph

Run `docket graph` in a terminal to use the native viewer when
`graph/docket-graph` is present. It shows a compact, selectable tree and a
detail pane. Use these keys:

| Key | Action |
|---|---|
| `↑`/`k`, `↓`/`j` | Move through entries |
| `space`/`enter` | Collapse or expand a branch |
| `tab` | Switch between the tree and detail pane |
| `/` | Search IDs, kinds, states, text, choices, and costs |
| `q`/`Ctrl-C` | Quit |

When the detail pane is focused, `PgUp`/`Ctrl-U` and `PgDn`/`Ctrl-D` scroll it;
`h`/`left` and `l`/`right` move horizontally. Press `Enter` to apply a search
and `Esc` to cancel it.

Piped output stays static. Use `--no-interactive` or `--plain` to force static
output, or choose `--style forest`, `--style rail`, or `--style compact`.
`--pretty` forces colour. `--interactive` explicitly requires terminal stdin
and stdout. The native detail pane shows every justification set. Static graph
modes include retired entries. Forest and rail name additional supports;
compact is a first-support tree projection. The native detail pane distinguishes
complete `supports` formulas from `depends_on` prerequisites and shows derived
decision applicability. Static output keeps support sets in its projection and
shows `blocked_by` for unavailable decision prerequisites.

The hook examples use an absolute path. They do not require `PATH`.

`docket context --for gemini|copilot|cursor` prints the ledger inside that
harness's hook envelope. The examples below use it, so a hook needs no shell
pipe.

## Claude Code

Add the marketplace and install Docket:

```text
/plugin marketplace add NovusEdge/docket
/plugin install docket@NovusEdge
```

Start a new session after installation. The plugin loads `hooks/hooks.json` and
the Docket skill.

## OpenAI Codex CLI

The repository contains `.codex-plugin/plugin.json`. Add the marketplace and
install Docket:

```sh
codex plugin marketplace add NovusEdge/docket
codex plugin add docket@NovusEdge
```

Start a new Codex task after installation. Codex loads the bundled skill and
session hook.

Set `DOCKET_AUTHOR=codex` in the hook environment when you require this author
name.
Docket uses automatic detection when the variable is absent.

## OpenCode

Create `~/.config/opencode/plugins/docket/index.ts`, or
`.opencode/plugins/docket/index.ts` for one project:

```js
import { execFileSync } from "node:child_process"

const PYTHON = "/usr/bin/python3"
const DOCKET = "/path/to/docket/bin/docket"

export const Docket = async () => {
  return {
    "experimental.chat.system.transform": async (input, output) => {
      try {
        const ledger = execFileSync(PYTHON, [DOCKET, "context"], {
          encoding: "utf8",
          env: { ...process.env, DOCKET_AUTHOR: "opencode" },
        })
        if (ledger.trim()) output.system.push(ledger)
      } catch {
        return
      }
    },
  }
}
```

A plugin is a named export. It is an async function that returns the hooks.
The hook adds the ledger to the system prompt before each model call.

The `Plugin.define` interface belongs to the OpenCode v2 API. That API is not
released.

Copy `skills/docket/SKILL.md` to `.opencode/skills/docket/SKILL.md`.
OpenCode also finds skills in `.agents/skills/`.

## Gemini CLI

Put this in `~/.gemini/settings.json`, or in `.gemini/settings.json` for one
project:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "name": "docket",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/docket/bin/docket context --for gemini",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

The entry has no `matcher`. A lifecycle matcher is an exact string, so a regular
expression matches no event.

The timeout is in milliseconds.

Gemini identifies a hook by its name and its command. It asks you to trust the
hook again after the command changes.

Copy `skills/docket/SKILL.md` to `.gemini/skills/docket/SKILL.md`.

## GitHub Copilot CLI

Put this in `.github/hooks/sessionStart.json` for a repository, or
`~/.copilot/hooks/sessionStart.json` for yourself:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "type": "command",
        "bash": "DOCKET_AUTHOR=copilot /path/to/docket/bin/docket context --for copilot",
        "powershell": "$env:DOCKET_AUTHOR=\"copilot\"; & \"C:\\Path\\To\\python.exe\" \"C:\\path\\to\\docket\\bin\\docket\" context --for copilot",
        "timeoutSec": 5
      }
    ]
  }
}
```

Copilot parses the hook output as JSON. It adds `additionalContext` to the model
context.

Copilot runs the `bash` field on Linux and macOS. It runs the `powershell` field
on Windows. PowerShell requires the call operator `&` before a quoted command
path.

For instructions, Copilot reads `.github/copilot-instructions.md`. Copy the body
of `skills/docket/SKILL.md` into it.

## Cursor

Use two files to install Docket for Cursor.

Hook, in `.cursor/hooks.json` for the project or `~/.cursor/hooks.json` for
yourself:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "command": "/path/to/docket/bin/docket context --for cursor"
      }
    ]
  }
}
```

Cursor calls its output field `additional_context`.

Instructions go in `.cursor/rules/docket.mdc`. The file requires this
frontmatter, or Cursor does not load it in every session:

```text
---
alwaysApply: true
---
```

## A harness with no hooks

Without a session-start hook, the harness cannot run a command for each session.
Write a current ledger snapshot to the instruction file:

```sh
docket context > DOCKET_CONTEXT.md
```

Configure the harness to load `DOCKET_CONTEXT.md`. Regenerate the file after each
decision.

## Which instruction file each harness reads

| Harness | Instruction file | Reads AGENTS.md by default |
|---|---|---|
| Claude Code | `CLAUDE.md`, plugin skills | no |
| Codex CLI | `AGENTS.md` | yes |
| Gemini CLI | `GEMINI.md`, configurable | no, `contextFileName` can point at it |
| Copilot CLI | `.github/copilot-instructions.md` | no |
| Cursor | `.cursor/rules/*.mdc` | no |

Only Codex reads `AGENTS.md` without configuration.

## Integration references

- [OpenCode plugins](https://opencode.ai/v2/docs/build/plugins/)
- [OpenCode agent skills](https://opencode.ai/docs/skills)
- [Gemini CLI hooks](https://geminicli.com/docs/hooks/reference/)
- [Gemini CLI extensions](https://geminicli.com/docs/extensions/reference/)
- [GitHub Copilot CLI hooks](https://docs.github.com/en/copilot/reference/hooks-reference)
- [Cursor hooks](https://prod.cursor.com/docs/hooks)
- [OpenAI Codex plugins](https://help.openai.com/en/articles/20001256/)

## Verification limits

The Go installer has planner and execution tests that use temporary homes.
`just verify` covers an install and uninstall roundtrip with a temporary home
and source checkout. Its Linux terminal flow is checked with tmux. Cross-build
checks cover Linux, macOS, and Windows binaries for amd64 and arm64; they do not
verify native macOS terminal behavior, Windows registry writes, or a live
installation on those systems.

The harness examples are configuration examples; the repository does not run a
live harness session for them. They were checked against their official formats
on 11 September 2026; the OpenCode example uses the v1 plugin interface.
