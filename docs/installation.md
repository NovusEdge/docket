# Installation

Docket requires Python 3.10 or later. It has no Python package dependencies.

An agent harness needs two integrations:

1. A session-start hook runs `docket context` and adds its output to the model context.
2. An instruction document tells the model when to record a decision.

All integrations use the same ledger. A project can therefore use more than one
agent harness.

## The installer

```sh
curl -fsSLO https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py
python3 install.py
```

`curl -O` saves the file as `install.py` in the current directory, whatever the
depth of the URL. From a checkout, run `python3 installer/install.py`.

The installer clones the repository if you do not run it from a checkout. It
adds the command to `PATH`, and it configures each harness that it finds.

An update clones into a temporary directory and swaps the result into place, so
a local change in the install directory never blocks it.

In a terminal, and without `--yes`, `--no-tty`, `--dry-run`, or `--harness`,
the installer runs a guided flow instead of taking every default silently.

On Linux and macOS it fetches a small Textual-based interface for that flow:
a venv under `$XDG_CACHE_HOME/docket/venv` (or `~/.cache/docket/venv`), created
on first use and reused after. If the venv can't be created or `pip install`
fails -- no network, PyPI blocked, a proxy -- the installer prints one warning
naming the reason and falls back to the same flow as plain prompts. Windows
always uses prompts: Textual's inline render mode does not exist there, and
running it full-screen would need Windows Terminal and would erase the
installer's own on-screen record when it exits.

Either way, the flow asks the same four things:

1. Where to put the `docket` command, showing the resolved default.
2. Which harnesses to configure, each with its detection result. Detected
   ones start selected. An undetected harness can still be selected, for a
   tool you are about to install.
3. If the chosen location is not already on `PATH`, it shows the exact line
   and file and asks before appending.
4. The full plan, for confirmation before writing anything.

Ctrl-C, or cancelling in the interface, exits without writing anything.

| Option | Effect |
|---|---|
| `--dry-run` | Print every file without writing it, non-interactively |
| `--harness NAME` | Configure one harness; repeat for more; skips the guided flow |
| `--project` | Configure this repository instead of your home directory |
| `--prefix DIR` | Put the command in `DIR` |
| `--yes` | Take every default and do not prompt |
| `--no-tty` | Treat stdin as non-interactive, same effect as `--yes` on prompting |
| `--uninstall` | Remove what the installer wrote |

CI and `just verify` use `--yes` (or a non-tty stdin), which keeps taking every
default with no prompts and no rc-file write, exactly as before.

The uninstall keeps every ledger.

Run the installer again to update.

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

The hook examples use an absolute path. They do not require `PATH`.

`docket context --for gemini|copilot|cursor` prints the ledger inside that
harness's hook envelope. The examples below use it, so a hook needs no shell
pipe.

## Claude Code

This integration has a live test.

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

The Claude Code path has a live test.

The installer runs the Codex commands and they succeed. The commands match the
CLI help available on 11 September 2026.

The OpenCode plugin shape matches the v1 plugin interface in the OpenCode
repository on that date.

The other examples match their official formats on that date. This repository
does not have live integration tests for them.

The installer runs on Linux and macOS in the same code path. Its Windows path
plans the correct files under test, but no test applies them on Windows.
