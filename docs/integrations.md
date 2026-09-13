# Agent setup reference

Use this page to configure an agent manually or inspect the files that connect it
to Docket. For guided setup, start with [Installation](installation.md). For daily
use, read [Working with your agent](agents.md). For an agent carrying out setup
on the user's behalf, follow [Setup instructions for agents](agent-setup.md).

## Configure an agent harness

Each section below gives the hook and instruction files for one harness.
Replace example paths with the absolute paths on your machine. Check that the
selected Python interpreter is version 3.11 or later. Quote paths that contain
spaces, and merge hook entries into existing configuration instead of replacing
the file.

`docket context --for gemini|copilot|cursor` wraps the ledger in the selected
harness's hook envelope. The examples use this form, so a hook needs no shell
pipe.

### Claude Code

Add the marketplace and install Docket:

```text
/plugin marketplace add NovusEdge/docket
/plugin install docket@NovusEdge
```

Start a new session after installation. The plugin loads `hooks/hooks.json` and
the Docket skill.

### OpenAI Codex CLI

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

### OpenCode

Create `~/.config/opencode/plugins/docket.ts`, or
`.opencode/plugins/docket.ts` for one project. These locations follow the
[OpenCode plugin guide](https://opencode.ai/docs/plugins/).

The installer writes `plugins/docket.ts` for you. Its
[plugin loader](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/config/plugin.ts)
scans files directly inside `plugins/`, so a file one level down is never
discovered.

Installers before 0.11.0 wrote `plugins/docket/index.ts`, which OpenCode never
loaded. A new install or an update removes that file. Keep one active copy to
avoid duplicate context.

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

This example uses the named-export plugin interface and the experimental
`chat.system.transform` hook. Check the interface when upgrading OpenCode.

Copy `skills/docket/SKILL.md` to `.opencode/skills/docket/SKILL.md`.
OpenCode also finds skills in `.agents/skills/`.

### Gemini CLI

Put this in `~/.gemini/settings.json`, or in `.gemini/settings.json` for one
project:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "name": "docket",
            "command": "/path/to/docket/bin/docket context --for gemini",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

The entry has no `matcher`, so it applies to each session-start event. Gemini's
[hook reference](https://geminicli.com/docs/hooks/reference/) uses exact strings
for lifecycle matchers and regular expressions for tool matchers.

The timeout is in milliseconds.

Copy `skills/docket/SKILL.md` to `.gemini/skills/docket/SKILL.md`.

### GitHub Copilot CLI

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

### Cursor

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
frontmatter to make the rule apply automatically:

```text
---
alwaysApply: true
---
```

### A harness with no hooks

Without a session-start hook, the harness cannot run a command for each session.

1. Write a current ledger snapshot to the instruction file:

   ```sh
   docket context > DOCKET_CONTEXT.md
   ```

2. Configure the harness to load `DOCKET_CONTEXT.md`.
3. Regenerate the file after each decision.

## Instruction files

Use the instruction or skill location described for each tool above. Those
locations configure Docket; they are not a complete list of every instruction
format an agent tool supports.

## Integration references

- [OpenCode plugins](https://opencode.ai/docs/plugins/)
- [OpenCode agent skills](https://opencode.ai/docs/skills)
- [Gemini CLI hooks](https://geminicli.com/docs/hooks/reference/)
- [GitHub Copilot CLI hooks](https://docs.github.com/en/copilot/reference/hooks-reference)
- [Cursor hooks](https://cursor.com/docs/hooks)
- [OpenAI Codex plugins](https://learn.chatgpt.com/docs/plugins)

## Verification scope

The Gemini, Copilot, and Cursor hook formats were checked against the linked
references on 13 September 2026. The Codex plugin commands were checked against
the installed CLI help. The OpenCode example follows its documented plugin
location and named-export interface.

These checks do not establish that a live session in every tool loads the
briefing. After manual setup, start a new session and check that the agent can
read your project's Docket context.
