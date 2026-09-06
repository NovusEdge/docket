# Installation

Docket needs two things from a harness.

1. A session-start hook that runs `docket context` and puts its output in front
   of the model.
2. An instruction document that tells the model when to record a decision.

The command itself is one Python 3 file with no dependencies, so it runs
anywhere. Only the two integration points differ per harness.

Every harness below reads the same ledger, so one project can be worked on from
several tools without the decisions diverging.

## The command

Clone the repository, then point the harness at `bin/docket`.

```sh
git clone https://github.com/NovusEdge/docket ~/Projects/docket
```

Optionally put it on `PATH` for your own shell use:

```sh
ln -s ~/Projects/docket/bin/docket ~/.local/bin/docket
```

The hooks below call the file by absolute path, so `PATH` is not required.

## Claude Code

```text
/plugin marketplace add NovusEdge/docket
/plugin install docket@NovusEdge
```

The plugin ships `hooks/hooks.json`, which Claude Code loads by convention, and
`skills/docket/SKILL.md`.

## OpenAI Codex CLI

Codex reads `.codex-plugin/plugin.json`, which this repository ships. It points
at the same `hooks/hooks.json` and `skills/` directory that Claude Code uses,
because the hook schemas are compatible.

To wire it up by hand instead, put this in `~/.codex/hooks.json` or
`<repo>/.codex/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/docket/bin/docket context"
          }
        ]
      }
    ]
  }
}
```

A `SessionStart` hook's stdout becomes extra developer context. Plain text works.

For instructions, Codex reads `AGENTS.md` from `~/.codex/AGENTS.md` and from the
repository, with files closer to the working directory winning. Copy the body of
`skills/docket/SKILL.md` into `AGENTS.md`, or install the plugin and let it use
the bundled skill.

## OpenCode

Add the plugin to `opencode.json` in the project or in
`~/.config/opencode/`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["./.opencode/plugins/docket.mjs"]
}
```

Then create `.opencode/plugins/docket.mjs`:

```js
import { execFileSync } from 'child_process';

const DOCKET = '/path/to/docket/bin/docket';

export const docket = async () => ({
  'before_agent_start': async (_input, output) => {
    let ledger = '';
    try {
      ledger = execFileSync('python3', [DOCKET, 'context'], { encoding: 'utf8' });
    } catch (e) {
      return;
    }
    if (ledger.trim()) output.systemPrompt.push(ledger);
  },
});
```

OpenCode has no separate skill format. The instruction document rides along in
the system prompt or in the project's context file.

## Gemini CLI

Create `gemini-extension.json` at the extension root:

```json
{
  "name": "docket",
  "version": "0.5.0",
  "contextFileName": "AGENTS.md"
}
```

`contextFileName` defaults to `GEMINI.md`. Repointing it at `AGENTS.md` lets one
instruction file serve Gemini and Codex.

Gemini CLI supports hooks in `hooks/hooks.json` inside the extension, with
`${extensionPath}` substitution. Check the current event names in Gemini's hook
reference before writing one. This document does not state a session-start event
name for Gemini, because that name was not verified against a primary source.

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
        "bash": "python3 /path/to/docket/bin/docket context | python3 -c 'import json,sys; print(json.dumps({\"additionalContext\": sys.stdin.read()}))'",
        "timeoutSec": 5
      }
    ]
  }
}
```

Copilot parses the hook's stdout as JSON and injects `additionalContext`.

For instructions, Copilot reads `.github/copilot-instructions.md`. Copy the body
of `skills/docket/SKILL.md` into it.

## Cursor

Cursor supports both pieces but has no packaging format, so this is a two-file
manual install.

Hook, in `.cursor/hooks.json` for the project or `~/.cursor/hooks.json` for
yourself:

```json
{
  "hooks": {
    "sessionStart": [
      {
        "command": "python3 /path/to/docket/bin/docket context | python3 -c 'import json,sys; print(json.dumps({\"additional_context\": sys.stdin.read()}))'"
      }
    ]
  }
}
```

Cursor's field is `additional_context`, with an underscore, unlike Copilot's
`additionalContext`.

Instructions go in `.cursor/rules/docket.mdc`, which Cursor includes in every
session.

## A harness with no hooks

Without a session-start hook there is no way to run a fresh command per session.
Put a snapshot of the ledger into whatever file that harness always loads:

```sh
docket context >> AGENTS.md
```

This goes stale as soon as a decision is recorded, so regenerate it. A hook is
better wherever one exists.

## Which instruction file each harness reads

| Harness | Instruction file | Reads AGENTS.md by default |
|---|---|---|
| Claude Code | `CLAUDE.md`, plugin skills | no |
| Codex CLI | `AGENTS.md` | yes |
| Gemini CLI | `GEMINI.md`, configurable | no, `contextFileName` can point at it |
| Copilot CLI | `.github/copilot-instructions.md` | no |
| Cursor | `.cursor/rules/*.mdc` | no |

`AGENTS.md` is a real cross-harness convention in 2026, and its coverage is
uneven. Only Codex reads it without configuration.

## Verification limits

The Claude Code path is tested. The Codex, OpenCode, Gemini, Copilot, and Cursor
configurations here follow each harness's documented format and have not been
run against a live install. Report anything that fails.
