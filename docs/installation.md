# Installation

Docket requires Python 3.10 or later. It has no Python package dependencies.

An agent harness needs two integrations:

1. A session-start hook runs `docket context` and adds its output to the model context.
2. An instruction document tells the model when to record a decision.

All integrations use the same ledger. A project can therefore use more than one
agent harness.

## The command

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

Create `.opencode/plugins/docket/index.ts`:

```js
import { execFileSync } from "node:child_process"
import { Plugin } from "@opencode-ai/plugin"

const DOCKET = "/path/to/docket/bin/docket"

export default Plugin.define({
  id: "docket",
  async setup(ctx) {
    const registration = await ctx.session.hook("context", (event) => {
      try {
        const ledger = execFileSync("python3", [DOCKET, "context"], {
          encoding: "utf8",
          env: { ...process.env, DOCKET_AUTHOR: "opencode" },
        })
        if (ledger.trim()) event.system.push({ text: ledger })
      } catch {
        return
      }
    })
    return () => registration.dispose()
  },
})
```

OpenCode loads local plugins from `.opencode/plugins/`. The context hook adds the
ledger before each model call.
It also adds the ledger after compaction.

Copy `skills/docket/SKILL.md` to `.opencode/skills/docket/SKILL.md`.
OpenCode also finds skills in `.agents/skills/`.

## Gemini CLI

Create `.gemini/settings.json` in the project:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .gemini/hooks/docket-context.py",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

Create `.gemini/hooks/docket-context.py`:

```python
import json
import os
import subprocess

env = dict(os.environ)
env["DOCKET_AUTHOR"] = "gemini"

result = subprocess.run(
    ["python3", "/path/to/docket/bin/docket", "context"],
    capture_output=True,
    check=False,
    env=env,
    text=True,
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": result.stdout,
    }
}))
```

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
        "bash": "DOCKET_AUTHOR=copilot python3 /path/to/docket/bin/docket context | python3 -c 'import json,sys; print(json.dumps({\"additionalContext\": sys.stdin.read()}))'",
        "timeoutSec": 5
      }
    ]
  }
}
```

Copilot parses the hook output as JSON. It adds `additionalContext` to the model
context.

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
        "command": "DOCKET_AUTHOR=cursor python3 /path/to/docket/bin/docket context | python3 -c 'import json,sys; print(json.dumps({\"additional_context\": sys.stdin.read()}))'"
      }
    ]
  }
}
```

Cursor calls its output field `additional_context`.

Instructions go in `.cursor/rules/docket.mdc`, which Cursor includes in every
session.

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

The Codex commands match the CLI help available on 7 September 2026.

The other examples match their official formats on that date. This repository
does not have live integration tests for them.
