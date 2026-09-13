# Installer reference

Use this page for custom install locations, unattended setup, source builds, and
installer behavior. For the normal setup and update steps, see
[Installation](installation.md). Manual agent configuration is in the
[agent setup reference](integrations.md).

## The installer

### Choose an installer path

- Download and run the compatibility launcher:

   ```sh
   curl -fsSLO https://raw.githubusercontent.com/NovusEdge/docket/main/installer/install.py
   python3 install.py
   ```

   `curl -O` saves the file as `install.py` in the current directory. Outside a
   checkout, the launcher downloads a native installer and verifies it against
   the release's `SHA256SUMS` file before running it. Release recipes build
   Linux, macOS, and Windows assets for amd64 and arm64. The matching asset must
   be published for the launcher to use it. Set `DOCKET_INSTALLER_VERSION` to
   select a published release tag.

- Run from an existing source checkout:

   ```sh
   python3 installer/install.py
   ```

   This builds the native installer locally with Go 1.26 or later and runs it
   against that checkout. Use `just installer-build` to build it without
   running it. The Go module, installer code, and installer tests live in
   `installer/`.

The installer clones the repository when you run it outside a checkout. It
adds the command to `PATH` and, by default, configures Claude Code and any
other harnesses it detects.

OpenCode currently needs a [manual plugin file placement step](integrations.md#opencode)
after installation.

### Verify the installation

After installation, check the version and active ledger:

```sh
docket --version
docket where
```

The session-start hook runs `docket context`. A harness can pass `--query`,
repeat `--file`, and set `--max-chars` for a task. Without a query, the output
serves as startup context. Docket measures the budget in characters and accepts
budgets from 512 characters upward. `--all` removes relevance filtering while
keeping the budget.

### Managed checkout behavior

The normal managed flow clones into a temporary directory and swaps the result
into place. It preserves a `.docket` ledger inside the managed checkout and
replaces other local changes in that checkout. An unrelated nonempty directory
is rejected. Running from an existing source checkout installs that checkout
without replacing it.

The native installer uses Bubble Tea, Bubbles, and Lip Gloss for its guided
flow and prepares the native `docket-graph` viewer. It builds the viewer from
the checkout when Go is available. Without Go, it fetches the matching viewer
asset and verifies `GRAPH-SHA256SUMS`; the asset must be published for the
checked-out version. The repository contains release recipes for these assets,
but building them does not publish a release.

In a terminal, the installer uses a guided flow unless you pass `--yes`,
`--no-tty`, `--dry-run`, `--update`, or `--harness`. It runs inline on an interactive
terminal and leaves the result in scrollback. Unattended runs use plain output.
The launcher creates no Python environment and installs no Python packages.

### Guided flow

For an installation, the guided flow proceeds through these steps:

1. Choose where to put the `docket` command and, for a downloaded installer,
   its checkout.
2. Select the harnesses to configure. Each shows its detection result, and
   detected harnesses start selected. You can also select a harness you plan
   to install later.
3. If the chosen location needs a `PATH` change, review the exact change and
   confirm whether to apply it. Unix installations show the shell line and
   destination file; Windows installations show the User PATH directory.
4. Review the full plan, including checkout updates and external commands,
   then confirm installation.

Cancelling before confirmation leaves the installation unchanged. Cancelling
during installation stops further actions; completed actions remain applied.

### Installer options

| Option | Effect |
|---|---|
| `--dry-run` | Print every planned operation without applying it |
| `--harness NAME` | Configure one harness; repeat for more; skips the guided flow |
| `--project` | Put the Claude skill and Cursor rule in this repository; hook configs keep user scope |
| `--prefix DIR` | Put the command in `DIR` |
| `--dir DIR` | Put the managed checkout in `DIR` |
| `--checkout DIR` | Use an existing source checkout without replacing it |
| `--yes` | Take every default and do not prompt |
| `--no-tty` | Treat stdin as non-interactive and apply the same prompt defaults as `--yes` |
| `--update` | Refresh the existing Docket checkout and native graph viewer; keep harness and PATH configuration unchanged |
| `--uninstall` | Remove what the installer wrote |
| `--version` | Print the installer version |

`--yes` and non-interactive runs apply defaults, including a needed `PATH`
change. Use `--dry-run` to inspect those changes first. `just verify` tests
installation and removal in a temporary home.

The uninstall keeps every ledger.

After installation, `docket`, `docket -h`, and `docket --help` print the version
and full top-level command help. Use `docket --version` for the concise version
only.

### Update, uninstall, and cleanup

For a managed install, run the downloaded launcher with `--update` to
fast-forward the managed checkout and refresh its viewer. The command must
already be installed. This mode leaves `PATH` entries and harness configuration
unchanged. Add `--dry-run` to review the checkout and viewer operations first.
It cannot be combined with `--harness`, `--project`, or `--uninstall`.

From a source checkout, `python3 installer/install.py --update` uses that
checkout and does not fetch Git. It refreshes the viewer when Go is available.
`just update` runs this source-checkout path. An explicit `--checkout DIR` also
uses that source tree without replacing it.

`just clean` removes repository build outputs, release outputs, and Python
caches. It preserves source files, `.docket` ledgers, configuration, and shared
Go caches.

Installing a Claude or Codex plugin from this repository does not download a
compiled viewer. For a source checkout with Go installed, run `just graph-build`
or run the installer against that checkout. If no viewer is available,
`docket graph` uses its compact text fallback in automatic terminal mode and
prints installation guidance. It does not access the network or invoke Go
while displaying a graph.

## Manual installation

Use this path when you want to manage the checkout yourself:

1. Clone the repository:

   ```sh
   git clone https://github.com/NovusEdge/docket.git ~/Projects/docket
   ```

2. Add the command to `PATH` if you want to use it in a shell:

   ```sh
   mkdir -p ~/.local/bin
   ln -s ~/Projects/docket/bin/docket ~/.local/bin/docket
   ```

3. To enable the interactive graph viewer, install Go 1.26 or later and run
   this from the source checkout:

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

## Verification limits

The Go installer has planner and execution tests that use temporary homes.
`just verify` covers an install and uninstall roundtrip with a temporary home
and source checkout. Its Linux terminal flow is checked with tmux. Cross-build
checks cover Linux, macOS, and Windows binaries for amd64 and arm64; they do not
verify native macOS terminal behavior, Windows registry writes, or a live
installation on those systems.

Manual agent configurations and their verification date are documented in the
[agent setup reference](integrations.md).
