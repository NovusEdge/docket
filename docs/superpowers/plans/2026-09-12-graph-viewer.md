# Interactive graph implementation plan

> Use subagent-driven-development to implement and review the scoped tasks. Include the existing installer port. The user authorized committing, pushing, and opening a PR; release publishing remains outside scope.

**Goal:** Make a readable interactive viewer the default for `docket graph` on a terminal.

**Approved design:** Compact decision rows, branch collapse, keyboard navigation, search, and a separate detail pane. Overview labels truncate to terminal width; details wrap without splitting words. Piped output remains text. The ledger CLI remains Python.

**Architecture:** A separate Go module in `graph/` builds `docket-graph`. Python owns ledger discovery, compatibility normalization, filtering, and retirement calculation. It writes a private temporary JSON document and starts the viewer with inherited terminal handles. The installer prepares the viewer in the checkout; runtime graph invocation performs no network requests.

**Stack:** Match installer pins: Go 1.26.0, Bubble Tea v2.0.9, Bubbles v2.2.1, Lip Gloss v2.0.6, x/ansi v0.11.8.

## Contract and constraints

- Native invocation: `docket-graph --data PATH [--plain]`; `--version` reports the build version.
- Input: `{"version":1,"entries":[{"id":"d1","state":"settled","question":"...","answer":"...","cost":"...","sets":[["d2","d3"],["d4"]],"supports":["d2","d3","d4"],"retired_by":""}]}`. Entries are normalized by Python; sets preserve AND within each set and OR between sets.
- Expected checkout executable: `graph/docket-graph` (Windows `.exe`). Source builds: `cd graph && go build -o docket-graph .`.
- Default interactive only with terminal stdin and stdout. `--no-interactive`, `--plain`, and explicit `--style` retain static renderers; explicit `--interactive` requests the viewer and requires a terminal. Piping never opens the viewer.
- Missing viewer in auto mode: concise installation/build guidance on stderr and compact text fallback. Explicit interactive mode fails clearly. Never download or compile implicitly during graph use.
- Keep every visible entry once in the overview, including retired entries. First visible support supplies the tree parent; detail shows all justification sets and retirement. Handle malformed cycles without infinite recursion or missing nodes.
- At narrow widths use stacked panes. Keep terminal control sequences in ledger content from controlling the terminal. Keep overview and detail within viewport bounds, including Unicode labels.
- Preserve context-hook behavior and avoid new global configuration or real-home installation. The user later authorized superseding stale local ledger entries and committing, pushing, and opening a PR; do not publish a release.
- Additional user request: bare `docket` prints version and full top-level help with exit status 0; `-h`/`--help` show the same output. Unknown commands remain errors and `--version` stays concise.
- Additional user request: installer `--update` and `just update` refresh only Docket and its native graph viewer. Preserve harness configuration, hooks, skills, and PATH; support dry-run. An explicit source checkout remains untouched by Git; managed checkout updates use the existing fast-forward policy.
- Additional user request: `just clean` removes repository binaries, release outputs and Python caches, preserving source, ledgers, configuration and shared Go caches. Verify cleanup only in a throwaway copy during development.
- Refresh the installation and related documentation. Keep richer decision metadata and dependency-editing changes for a later branch, as requested.

## Tasks

- [x] Implement `graph/` viewer and model/layout tests. Owner: Luna high.
- [x] Integrate default TTY dispatch and bare-command help in `bin/docket`. Python tests and Sol review pass.
- [x] Deliver viewer through installer, update-only mode, clean/build/release recipes and user documentation. Owner: Luna high.
- [x] Address Sol review findings, complete tmux captures, verify temporary-home installation and native build targets.

## Review and verification record

- Python routing/help: reviewed clean after testing native launch errors and correcting the version helper documentation. A present but broken viewer fails clearly; only a missing viewer gets the automatic text fallback.
- Temporary-home installation, update dry-run, update without settings or PATH changes, and uninstall passed.
- Viewer fixes reviewed clean: selection offset reset, C1 containment, correct ancestor connectors, tiny viewport bounds, essential help, leaf collapse, and retired-state labels.
- Installer fixes reviewed clean: checkout update precedes the viewer; cleanup preserves targets behind symlinked parent directories.
- Documentation review passed after correcting the description of compact mode's omitted support edges.
- Final local checks: `just test`, both Go vets, six-target builds for both native components with checksum verification, and tmux captures at 120/80/60 columns with terminal restoration.
- Local ledger entries d37-d41 supersede five stale installer decisions. d18 remains open because automatic justification expansion still has no chosen bound.

## Validation

Viewer tests cover selection, collapse, search, scrolling, resize, Unicode bounds, grouped supports, retirement, filtered supports and cycles. Python tests cover TTY routing, flags, temporary-file cleanup, native process errors, and pipe compatibility. Installer checks cover source/prebuilt acquisition, checksums, dry-run and uninstall ownership. Run graph and installer Go tests/vet, Python CLI and bootstrap tests, cross-build native targets, and inspect actual terminal captures. Report native Mac/Windows execution as untested unless exercised.
