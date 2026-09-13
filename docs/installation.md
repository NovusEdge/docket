# Installation

Install Docket, choose the agent tools you want to connect, and check that the
command works.

You need **Python 3.11 or later**, Git, and an internet connection for the
download. Docket has no Python package dependencies. A normal downloaded
installation does not require Go.

## The installer

### Linux and macOS

Run these commands in a folder outside an existing Docket source checkout:

```sh
curl -fsSLO https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py
python3 install.py
```

This saves `install.py` in the current folder and runs it. The launcher downloads
the installer for your platform and checks its release checksum.

### Windows

In PowerShell, download the same file and run it with Python:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py -OutFile install.py
py -3 install.py
```

If you use `python` instead of the `py` launcher, run `python install.py`.
Make sure it selects Python 3.11 or later.

### Follow the setup

In an interactive terminal, the installer lets you choose the command location
and agent tools. Review any proposed PATH change and the installation plan, then
confirm it.

The installer adds the `docket` command and prepares the graph viewer. Keep the
downloaded `install.py` file if you want to use it for updates or removal later.

Custom locations and unattended setup are covered in the
[installer reference](installer-reference.md#installer-options).

## Check that it works

Open a new terminal and run:

```sh
docket --version
docket where
```

The first command prints the installed version. The second prints the active
ledger's location. It can say `not created yet` before you record anything or
run `docket init`.

Start a new agent session after installation so it can load the integration.

Continue with [Your first decision](quickstart.md) to create a project ledger.

## Configure an agent harness

During setup, select the tools you use. Docket supports Claude Code, Codex,
Gemini CLI, GitHub Copilot CLI, Cursor, and OpenCode.

For OpenCode, complete the [plugin file placement step](integrations.md#opencode)
after installation so it can find the integration.

For daily use, read [Working with your agent](agents.md). For plugin commands,
hook configuration, and instruction files, see the
[agent setup reference](integrations.md).

## Update, uninstall, and cleanup

### Update a downloaded installation

From the folder containing the downloaded `install.py`, run:

```sh
python3 install.py --update --dry-run
python3 install.py --update
```

On Windows, use `py -3` in place of `python3`.

The first command previews the update. The second updates the managed checkout
and refreshes the graph viewer. Agent configuration and PATH settings stay as
they are.

If you installed in custom locations, use the same `--dir` and `--prefix`
values. There is no `docket update` command.

### Remove Docket

Use the downloaded launcher:

```sh
python3 install.py --uninstall
```

Use `py -3 install.py --uninstall` on Windows. Pass any custom locations you
used during installation.

Uninstall removes Docket's integration and command files. It keeps your ledgers.
See the [installer reference](installer-reference.md#update-uninstall-and-cleanup)
for source-checkout updates and build cleanup.

## Manual installation

If you already have a Docket source checkout, run this from its root:

```sh
python3 installer/install.py
```

This path builds from your checkout and requires Go 1.26 or later as well as
Python. See [Source and manual setup](installer-reference.md#manual-installation)
for the full steps.

## Browse the decision graph

After you have recorded something, run:

```sh
docket graph
```

Select records in the tree to read their details. The
[reading guide](reading.md#browse-connected-records) explains the controls.

If you installed only the agent plugin, the viewer may be absent. Docket then
shows a text graph with setup guidance. Run the installer to prepare the viewer.

## If setup fails

| What you see | What to check |
|---|---|
| Python version error | Run `python3 --version` or `py -3 --version` and confirm it is at least 3.11 |
| Git is missing | Install Git and make sure `git --version` works in this terminal |
| `docket` is not found after setup | Open a new terminal and check the command location and PATH change from the installer |
| No download for your platform | Check the [release assets](https://github.com/NovusEdge/docket/releases/latest); downloads target Linux, macOS, and Windows on amd64 and arm64 |
| An update cannot fast-forward | Keep any local work and reconcile the managed checkout before retrying; see [managed checkout behavior](installer-reference.md#managed-checkout-behavior) |

## Verification limits

Release builds cover Linux, macOS, and Windows, but build success does not
establish that every native installation flow has been tested. The
[verification notes](installer-reference.md#verification-limits) describe the
checks and their limits.
