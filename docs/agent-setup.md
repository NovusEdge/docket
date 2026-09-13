# Setup instructions for agents

Use these instructions when a user asks you to set up Docket. The default setup
installs the terminal command, native graph viewer, and integration for the agent
the user is running.

For a plugin-only request, use the relevant
[Claude Code or Codex instructions](installation.md#configure-an-agent-harness)
instead. Plugin installation does not provide a shell command or compiled viewer.

## 1. Inspect the environment

Identify the current agent from the session's tools and configuration. Do not
select every installed agent. If the current agent is unclear, ask which one
the user wants to configure.

Check the operating system and architecture, Git, and Python. Docket requires
Python 3.11 or later. The launcher supports Linux, macOS, and Windows on amd64
and arm64. Go is not required for the downloaded installation.

Check whether Docket is already installed. Inspect the command location and
version before adding another copy. Keep any existing custom installation paths.

Use the user's project as the working directory. Setup does not require
`docket init`; create a shared project ledger only when the user asks for one.

## 2. Download the launcher

On Linux or macOS, download into a temporary folder:

```sh
docket_setup_dir="$(mktemp -d)" &&
curl -fsSL https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py \
  -o "$docket_setup_dir/install.py"
```

On Windows, use PowerShell:

```powershell
$docketSetupDir = Join-Path ([System.IO.Path]::GetTempPath()) ("docket-setup-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $docketSetupDir -ErrorAction Stop | Out-Null
$docketSetupScript = Join-Path $docketSetupDir "install.py"
Invoke-WebRequest https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py -OutFile $docketSetupScript -ErrorAction Stop
```

Keep the resulting path for subsequent commands. If your execution tool starts
a fresh shell for each call, use that absolute path instead of assuming the
variable survives into the next call.

Read the downloaded `install.py` before running it. It fetches a native installer
and verifies its checksum against the release's `SHA256SUMS`. Checksum validation
checks consistency with that release manifest; it is not a separate signature.

Keep the launcher outside a Docket source checkout. The native installer creates
the permanent checkout itself. Cloning the repository into a temporary folder
and running its installer would select a source build, require Go, and leave
installation paths pointing at a temporary checkout.

## 3. Select the integration and review the plan

Use the integration name for the current agent:

| Agent | Installer value |
|---|---|
| Claude Code | `claude-code` |
| Codex | `codex` |
| Gemini CLI | `gemini` |
| Cursor | `cursor` |
| GitHub Copilot CLI | `copilot` |
| OpenCode | `opencode` |

For example, to inspect a Gemini CLI setup on Linux or macOS:

```sh
python3 "$docket_setup_dir/install.py" --harness gemini --dry-run
```

Substitute the current agent's value. On Windows, use
`py -3 $docketSetupScript` in place of `python3 "$docket_setup_dir/install.py"`.

Review the permanent checkout location, command location, PATH change, and agent
configuration. Add `--dir` and `--prefix` when the user has chosen custom paths.

The installer writes user-level integration by default. `--project` changes the
Claude skill and Cursor rule location, but hook configuration remains user-level.
Do not describe it as a fully project-local installation.

Passing `--harness` skips the interactive setup screen. The subsequent apply
command uses defaults without another prompt, so inspect the dry run first.
Follow the user's existing authorization and the environment's approval rules.
If the plan goes beyond what they asked for, explain the additional change.

## 4. Apply the reviewed setup

Run the same command without `--dry-run`:

```sh
python3 "$docket_setup_dir/install.py" --harness gemini
```

Repeat `--harness` only when the user requested several integrations.

For OpenCode, also follow the
[manual plugin file placement step](integrations.md#opencode). Check existing
files before moving anything. Keep one active plugin and report that the manually
placed file needs separate maintenance.

If an installation already exists and the user only wants an update, use
`--update --dry-run`, followed by `--update`. Do not combine `--update` with
`--harness`. Use the downloaded launcher for an installer-managed checkout;
source-checkout updates have different behavior.

## 5. Verify and report

Run the installed command by its full path if the current shell has not picked
up the PATH change yet:

```sh
docket --version
docket where
docket check
docket context
```

Run ledger checks from the user's project. An empty project can have no ledger
yet and produce no context; do not add sample records to make a check pass.

Confirm that the viewer binary exists at the path used by the installation.
Check the integration files or plugin registration without overwriting unrelated
settings. Do not treat a successful installation as proof that the current
conversation has refreshed its context.

Tell the user:

- Where Docket was installed and which integration was configured.
- Which checks passed and any step that still needs attention.
- To start a new agent session in the project and ask it to read Docket context.

The temporary launcher folder can be removed after setup. Keep the permanent
checkout and the user's ledger files.
