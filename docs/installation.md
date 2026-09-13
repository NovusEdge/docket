# Set up Docket

Docket works with Claude Code, Codex, Gemini CLI, GitHub Copilot CLI, Cursor, and
OpenCode. You can ask your agent to set it up or follow the steps for your tool.

## Requirements

| Install route | What you need |
|---|---|
| Ask your agent to set up Docket | Python 3.11+, Git, and an internet connection |
| Install the Claude Code or Codex plugin | That agent tool, Python 3.11+ available as `python3`, and Git |
| Run the downloaded installer | Python 3.11+, Git, and an internet connection |
| Build from a Git checkout | Python 3.11+, Git, and Go 1.26+ |

Docket has no Python package dependencies. The downloaded installer uses prebuilt
binaries when Go is absent, so you do not need Go for that route. The Unix
download example also uses `curl`; Windows uses PowerShell.

## Let your agent handle setup

Paste this into your agent:

> Set up Docket for the agent I am using in this project. Follow the instructions
> at https://raw.githubusercontent.com/NovusEdge/docket/main/docs/agent-setup.md.
> Check the installation and tell me what I need to do to start using it.

The [shared setup guide](agent-setup.md) tells the agent how to check your
environment, select its integration, review the installation plan, and verify
the result. It uses a permanent installation location and preserves existing
configuration.

After setup, start a new agent session in your project. You can then ask it to
record decisions or follow [Your first decision](quickstart.md).

## Configure an agent harness

If you prefer to do the setup yourself, choose your tool:

| Your tool | Setup |
|---|---|
| Claude Code | [Install the Claude Code plugin](#claude-code) |
| Codex | [Install the Codex plugin](#codex) |
| Gemini CLI | [Use the installer and select Gemini CLI](#gemini-cli-cursor-and-github-copilot-cli) |
| Cursor | [Use the installer and select Cursor](#gemini-cli-cursor-and-github-copilot-cli) |
| GitHub Copilot CLI | [Use the installer and select Copilot](#gemini-cli-cursor-and-github-copilot-cli) |
| OpenCode | [Install and place the OpenCode plugin](#opencode) |

### Claude Code

Run these commands inside Claude Code:

```text
/plugin marketplace add NovusEdge/docket
/plugin install docket@NovusEdge
```

The plugin includes the Docket skill and session hook. Its Python command must
be available as `python3`. Start a new session, then ask Claude to read the
Docket context.

See [Claude Code's plugin guide](https://code.claude.com/docs/en/discover-plugins)
for plugin management. If you also want `docket` in your terminal and the native
graph viewer, use [the installer](#the-installer).

### Codex

Run these commands in a terminal with the Codex CLI installed:

```sh
codex plugin marketplace add NovusEdge/docket
codex plugin add docket@NovusEdge
```

Start a new Codex task in your project, then ask it to read the Docket context.
The plugin includes the skill and session hook. Its hook uses `python3`.

The plugin alone does not add `docket` to your shell's PATH or install a compiled
graph viewer. Use [the installer](#the-installer) if you want those as well.

### Gemini CLI, Cursor, and GitHub Copilot CLI

Run [the installer](#the-installer) and select your tool in the setup screen.
You can select more than one if you use several agents.

The installer adds the command, prepares the graph viewer, and writes the
selected integrations. Start a new agent session after it finishes.

Manual hook configuration is in the [agent setup reference](integrations.md).

### OpenCode

Run [the installer](#the-installer) and select OpenCode. Then complete the
[plugin file placement step](integrations.md#opencode) so OpenCode can find it.

Start a new session after setup and ask OpenCode to read your Docket context.

## The installer

Use the installer for the terminal command, graph viewer, and agent integrations
in one setup. It downloads the release for your platform and clones Docket into
a permanent directory. You do not need to clone the repository yourself or
install Go.

### Linux and macOS

Download the launcher into a temporary folder:

```sh
docket_setup_dir="$(mktemp -d)" &&
curl -fsSL https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py \
  -o "$docket_setup_dir/install.py"
```

Then run it from the same terminal:

```sh
python3 "$docket_setup_dir/install.py"
```

The launcher checks the native installer's release checksum before running it.
In an interactive terminal, setup lets you select agent tools, review any PATH
change, and confirm the plan.

The temporary folder holds only the launcher. The installation normally lives
at `~/.local/share/docket`, with the command in `~/.local/bin`. If
`XDG_DATA_HOME` is set, the checkout defaults to `$XDG_DATA_HOME/docket`.
You can change either location during setup.

### Windows

In PowerShell, download the launcher to a new temporary folder:

```powershell
$docketSetupDir = Join-Path ([System.IO.Path]::GetTempPath()) ("docket-setup-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $docketSetupDir -ErrorAction Stop | Out-Null
$docketSetupScript = Join-Path $docketSetupDir "install.py"
Invoke-WebRequest https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py -OutFile $docketSetupScript -ErrorAction Stop
```

Then run it:

```powershell
py -3 $docketSetupScript
```

If you use `python` instead of the `py` launcher, run
`python $docketSetupScript`. It must select Python 3.11 or later.

The checkout normally lives at `%LOCALAPPDATA%\docket` on Windows.
`XDG_DATA_HOME`, when set, takes precedence. Review the destination and User
PATH change in the setup screen.

### Check that it works

Open a new terminal and run:

```sh
docket --version
docket where
```

The first command prints the installed version. The second prints the active
ledger's path. It can say `not created yet` before you record anything or run
`docket init`.

You can remove the temporary download folder after setup. Your installed
command and agent integrations use the permanent checkout.

## Update, uninstall, and cleanup

For a plugin-only installation, use that agent's plugin manager to update or
remove Docket.

For an installer-managed installation, download the launcher again using the
steps above, then run:

```sh
python3 "$docket_setup_dir/install.py" --update --dry-run
python3 "$docket_setup_dir/install.py" --update
```

On Windows, use `py -3 $docketSetupScript` in place of
`python3 "$docket_setup_dir/install.py"`.

The preview shows the proposed changes. The update refreshes the managed
checkout and graph viewer while keeping agent configuration and PATH settings.

To remove an installer-managed installation:

```sh
python3 "$docket_setup_dir/install.py" --uninstall
```

Use the same `--dir` and `--prefix` values if you installed in custom locations.
Uninstall keeps your ledgers. There is no `docket update` command.

Use the downloaded launcher for these operations. Running `installer/install.py`
inside the permanent checkout selects the source-build path and requires Go.

## Manual installation

If you want to manage the source with Git, clone it into a directory you will
keep. This path requires **Go 1.26 or later** as well as Python:

```sh
git clone https://github.com/NovusEdge/docket.git ~/Projects/docket
python3 ~/Projects/docket/installer/install.py
```

The installed command points into this checkout, so keep it in place. A clone
under `/tmp` would stop working when the temporary directory is removed.

Update the checkout with Git yourself before running its installer with
`--update`. That command rebuilds from the source you have; it does not fetch
updates for a source checkout.

The [installer reference](installer-reference.md) covers custom locations,
unattended setup, and build cleanup.

## Browse the decision graph

After recording something, run `docket graph`. With the native viewer installed,
you can select records in a tree and read their details. See
[Reading your ledger](reading.md#browse-connected-records) for the controls.

A plugin-only installation uses a text graph unless you separately prepare the
viewer. Your agent can run the bundled command even when `docket` is not on
your shell's PATH.

## If setup fails

| What you see | What to check |
|---|---|
| Python version error | Run `python3 --version` or `py -3 --version` and confirm it is at least 3.11 |
| Git is missing | Install Git and check that `git --version` works |
| `docket` is not found | A plugin-only install does not add a shell command. After using the installer, open a new terminal and check its PATH change |
| No download for your platform | Check the [release assets](https://github.com/NovusEdge/docket/releases/latest); downloads target Linux, macOS, and Windows on amd64 and arm64 |
| An update cannot fast-forward | Preserve local changes and reconcile the checkout before retrying; see [managed checkout behavior](installer-reference.md#managed-checkout-behavior) |

## Verification limits

The [installer verification notes](installer-reference.md#verification-limits)
and [integration checks](integrations.md#verification-scope) describe what was
tested. A successful build or setup command does not prove that a new agent
session has loaded the briefing.
