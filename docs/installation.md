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

Every command but `docket construct` runs on the standard library. Construct
needs a provider SDK, which the installer offers to set up and keeps in its own
virtualenv outside the checkout; that step needs
[uv](https://docs.astral.sh/uv/) and nothing else does. See
[Constructing on existing projects](construct.md).

The downloaded installer uses prebuilt binaries when Go is absent, so you do not
need Go for that route. The Unix download example also uses `curl`; Windows uses
PowerShell.

## Let your agent handle setup

Expand the prompt below, copy it, and paste it into your agent:

<details>

<summary>Copy setup prompt</summary>

```text
Set up Docket for the agent I am using in this project. Install the
terminal command, native graph viewer, and integration for this agent.

1. Identify the current agent, operating system, and architecture.
   Check for Python 3.11+ and Git. The downloaded installer does not
   require Go. Building from a source checkout requires Go 1.26+.
   If a requirement is missing, tell me what is needed.

2. Check whether Docket is already installed. Reuse its existing paths
   and preserve my configuration and ledger. Configure only the agent
   I am using. Ask which agent to configure if you cannot identify it.

3. Download the launcher below into a temporary directory outside any
   Docket source checkout, then read it before running it:
   https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py

   Let the installer create the permanent checkout. Do not install
   from a temporary clone or leave installed paths pointing into a
   temporary directory.

4. Use the launcher with --harness and the value for my agent:
   Claude Code: claude-code
   Codex: codex
   Gemini CLI: gemini
   Cursor: cursor
   GitHub Copilot CLI: copilot
   OpenCode: opencode

   Run it with Python 3.11+ from my project directory. On Linux or
   macOS, use python3; on Windows, use a suitable Python command such
   as py -3. Use the launcher's absolute path between shell calls.

5. Run with --dry-run first. Review the checkout location, command
   location, PATH changes, and agent configuration. Preserve custom
   paths with --dir and --prefix where needed. The default integration
   is user-level. Apply the reviewed setup by running the same command
   without --dry-run, following the environment's approval rules.

6. Check that the agent can discover its integration. For OpenCode,
   check plugin placement against the installed OpenCode version and
   keep one active copy. Preserve unrelated settings and report any
   manual step that remains.

7. From my project, run docket --version, docket where, docket check,
   and docket context. Use the installed command's full path if PATH
   has not refreshed. Confirm that the native viewer binary exists.
   An empty project may have no ledger or context yet. Do not create
   sample records or run docket init unless I ask for a shared ledger.

8. Tell me where Docket was installed, which integration was configured,
   and which checks passed. Explain anything that still needs attention.
   Remind me to start a new agent session in this project and ask it
   to read Docket context. Remove only the temporary launcher files
   created for this setup.
```

</details>

The prompt covers environment checks, installation, and verification. The
[setup reference for agents](agent-setup.md) has additional platform examples.

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

`docket` checks for a newer release once a day and prints a notice above your
agent's context briefing when one exists, naming the command for your install
shape. The check runs in a detached background process so it never delays a
session start; the result is cached at
`$XDG_STATE_HOME/docket/update.json` (`~/.local/state/docket/update.json` by
default). Set `DOCKET_NO_UPDATE_CHECK=1` to disable both the check and the
notice. Run `docket update --check` to ask directly, or `docket update` to
apply it.

For a plugin-only installation, `docket update` prints the plugin manager
command for your harness rather than changing anything itself; run that
command, or update through the harness yourself.

For an installer-managed installation, `docket update` is the short form.
Equivalently, download the launcher again using the steps above and run:

```sh
python3 "$docket_setup_dir/install.py" --update --dry-run
python3 "$docket_setup_dir/install.py" --update
```

On Windows, use `py -3 $docketSetupScript` in place of
`python3 "$docket_setup_dir/install.py"`.

The preview shows the proposed changes. The update refreshes the managed
checkout and graph viewer, refreshes the docket plugin in any harness where
it is also installed, and keeps agent configuration and PATH settings.

To remove an installer-managed installation:

```sh
python3 "$docket_setup_dir/install.py" --uninstall
```

Use the same `--dir` and `--prefix` values if you installed in custom locations.
Uninstall keeps your ledgers.

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
