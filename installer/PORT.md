# Go installer implementation plan

Approved scope: replace the installer with Go and Charm components, using
`~/vms/stoat/internal/installer/tui.go` as the interaction reference. Keep all
installer code, tests, dependencies, and build tools in `installer/`.

The ledger CLI remains Python 3.11+. The installer uses an inline transcript
with checks, location, harness selection, PATH consent, review, execution, and
results. The same planner feeds interactive and unattended execution. Review
includes filesystem changes, Codex commands, checkout updates, and registry
changes. Dry runs do not write. Uninstall preserves ledgers and unrelated config.

## Tasks

- [x] Port planning and platform execution; test idempotence,
  config preservation, explicit empty selections, dry runs, and uninstall.
- [x] Build the Bubble Tea flow with Bubbles components and Lip Gloss;
  test cancellation, selection, review, resizing, and errors.
- [x] Replace Textual bootstrap with a verified binary launcher and produce
  release binaries for Linux, macOS, and Windows; update recipes and docs.
- [x] Run focused Go/Python tests, cross-builds, temporary-home install and
  uninstall, tmux layout checks, and an independent code review.

## File ownership and interfaces

`types.go` defines `Options`, `Environment`, `Action`, `Plan`, and `Harness`.
`planner.go` supplies `BuildPlan(Environment, Options) (Plan, error)` and
`DetectHarnesses(Environment) []Harness`. Planning reads but never writes.
`runtime.go` supplies environment discovery and action execution. `tui.go`
supplies `RunTUI(Environment, Options) int`. `main.go` parses flags and selects
the TUI or plain output. The Go module and all related files live here.

`install.py` remains only as a compatibility launcher for existing download
commands. It runs a temporary, checksum-verified release binary or builds this
checkout when Go is available. It contains no harness or installation logic.

Verification uses temporary homes and fake external commands. Native Windows
and macOS runtime qualification is reported separately from cross-compilation.
