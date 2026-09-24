# Privacy policy

Last updated: 2026-09-24

Docket runs on your computer. It has no server, no account, and no telemetry.
The author of Docket does not collect, receive, or store any data from your use
of it.

## What Docket stores

Docket writes these files on your computer:

| File | Location | Contents |
|---|---|---|
| Ledger and feature store | `.docket/` in your project, or `~/.claude/docket/<project>/` when the project has no `.docket/` directory | The claims, decisions, and questions you or your agent record |
| Update state | `~/.local/state/docket/update.json` (`%LOCALAPPDATA%\docket-state` on Windows) | The latest release tag and when Docket last checked |

Each ledger record stores its text and these provenance fields:

- a timestamp
- the Git branch
- the agent session ID
- an author name

The author name is the value of `DOCKET_AUTHOR`, or the detected agent name.
When neither is available, Docket uses your operating system username (`$USER`).

The ledger leaves your computer only when you move it. If you commit `.docket/`
and push it, anyone with access to that repository can read it.

## Network requests

Docket makes network requests only in these cases:

- **Update check.** At most once a day, the session hook fetches
  `https://api.github.com/repos/NovusEdge/docket/releases/latest` to read the
  latest release tag. The request sends no ledger content or project
  information. GitHub receives your IP address and the request headers, as it
  does for any request. Set `DOCKET_NO_UPDATE_CHECK=1` to turn the check off.
- **`docket update` and the installer.** These download Docket from GitHub
  when you run them.
- **`docket construct`.** This command runs only when you invoke it. It sends
  the documents you name to the language model provider you configure, using
  your own API key. The providers are Anthropic, OpenAI, Google Gemini, and
  OpenRouter. That provider's privacy policy governs the data. `docket construct
  --dry-run` lists the documents it would send, without sending them.

## Your agent

Docket prints a briefing of ledger records into your agent's session. The agent
and its provider then handle that text under their own terms, the same as any
other text in the session.

## Changes

Changes to this policy are recorded in this file's Git history.

## Contact

Open an issue at https://github.com/NovusEdge/docket/issues.
