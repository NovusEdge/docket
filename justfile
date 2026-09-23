version := `cat VERSION 2>/dev/null || echo dev`
prefix := env_var_or_default("PREFIX", env_var("HOME") / ".local/bin")

# show available recipes
default:
    @just --list

# test the ledger, native installer, and download launcher
[group('dev')]
test:
    python3 tests/test_docket.py
    python3 -m unittest discover -s tests -p 'test_*.py'
    cd graph && go test ./...
    cd installer && go test ./...
    python3 -m unittest discover -s installer -p 'test_*.py'

# Pinned so a contributor's run and CI's run report the same findings. uvx and
# `go run` fetch these on demand, so neither is an install requirement.
ruff := "ruff@0.16.7"
golangci := "github.com/golangci/golangci-lint/v2/cmd/golangci-lint@v2.13.2"

# rewrite Python and Go to their canonical formatting
[group('dev')]
fmt:
    uvx {{ruff}} format .
    cd installer && go run {{golangci}} fmt ./...
    cd graph && go run {{golangci}} fmt ./...

# report every formatting, lint and type finding; change nothing
[group('dev')]
lint:
    uvx {{ruff}} format --check .
    uvx {{ruff}} check .
    uvx pyrefly check
    cd installer && go run {{golangci}} run ./...
    cd graph && go run {{golangci}} run ./...

# install and uninstall against a throwaway HOME, leaving this machine alone
[group('dev')]
verify:
    #!/usr/bin/env bash
    set -euo pipefail
    cd installer
    go test -run '^TestInstallUninstallRoundTripInTemporaryHome$' -v .

# wire this machine
[group('install')]
install:
    python3 installer/install.py

# refresh the checkout, graph viewer, and installed harness plugins
[group('install')]
update:
    python3 installer/install.py --update

# build the installer without running it
[group('dev')]
installer-build:
    cd installer && go build -o docket-installer .

# build the native graph viewer for this checkout
[group('dev')]
graph-build:
    cd graph && go build -o docket-graph .

# cross-build graph viewer release assets and GRAPH-SHA256SUMS
[group('release')]
graph-release:
    python3 graph/release.py

# remove repository build outputs and Python caches; preserve ledgers and source
[group('dev')]
clean:
    #!/usr/bin/env python3
    import os
    import shutil
    from pathlib import Path

    root = Path.cwd()

    def has_symlink_parent(target):
        current = root
        for part in target.relative_to(root).parts[:-1]:
            current /= part
            if current.is_symlink():
                return True
        return False

    for relative in (
        "installer/docket-installer",
        "installer/docket-installer.exe",
        "installer/installer",
        "installer/installer.exe",
        "graph/docket-graph",
        "graph/docket-graph.exe",
        "graph/graph",
        "graph/graph.exe",
        "dist",
    ):
        target = root / relative
        if has_symlink_parent(target):
            continue
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)

    cache_names = {"__pycache__", ".pytest_cache", ".ruff_cache"}
    for current, directories, _ in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        if ".git" in directories:
            directories.remove(".git")
        if ".docket" in directories:
            directories.remove(".docket")
        for name in list(directories):
            target = current_path / name
            if target.is_symlink():
                directories.remove(name)
                continue
            if name in cache_names:
                shutil.rmtree(target)
                directories.remove(name)

# cross-build installer release assets and SHA256SUMS
[group('release')]
installer-release:
    python3 installer/release.py

# print every file the installer would write, and write none of them
[group('install')]
dry:
    python3 installer/install.py --dry-run

# remove what the installer wrote; keeps every ledger
[group('install')]
uninstall:
    python3 installer/install.py --uninstall

# report the docket on PATH and the ledger active in this directory
[group('install')]
where:
    #!/usr/bin/env bash
    found=$(command -v docket || true)
    if [ -z "$found" ]; then
      echo "docket is not on PATH; this checkout is {{version}}"
    else
      # A docket that predates --version exits 2 with a usage error, which is
      # the signal that PATH points at an older copy than this checkout.
      echo "$found -> $("$found" --version 2>/dev/null || echo 'older than 0.6.4')"
    fi
    ./bin/docket where

# bump, roll the changelog, test, commit, tag, and push; CI publishes the release
[group('release')]
release new:
    #!/usr/bin/env bash
    set -euo pipefail
    # The ledger records decisions continuously and ships once per release, so
    # it is the one path allowed to be dirty here. Every other change belongs in
    # its own commit.
    dirty="$(git status --porcelain -- . ':(exclude).docket')"
    test -z "$dirty" || { echo "working tree is dirty outside .docket:"; echo "$dirty"; exit 1; }
    ./bin/docket check
    # Before anything is written. 0.13.0 shipped with its entry still under
    # Unreleased, so the refusal comes first and costs nothing when it passes.
    python3 scripts/roll_changelog.py "{{new}}" --date "$(date -u +%F)" --check
    # The bump has to precede the test, because a test compares the running
    # --version against VERSION. So a failing test would otherwise leave a
    # half-applied bump behind with nothing saying how to undo it. Cleared on
    # the commit below, which is the point of no return.
    bumped="VERSION CHANGELOG.md .claude-plugin/plugin.json .codex-plugin/plugin.json"
    trap 'echo "release aborted; restoring $bumped" >&2; git checkout -- $bumped' ERR INT TERM
    echo "{{new}}" > VERSION
    python3 scripts/roll_changelog.py "{{new}}" --date "$(date -u +%F)"
    # Rewritten as JSON, not by sed: a manifest that stops parsing takes the
    # plugin down in every harness at once.
    for f in .claude-plugin/plugin.json .codex-plugin/plugin.json; do
      python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["version"]=sys.argv[2]; open(p,"w").write(json.dumps(d, indent=2)+"\n")' "$f" "{{new}}"
    done
    just test
    git add VERSION CHANGELOG.md .claude-plugin/plugin.json .codex-plugin/plugin.json .docket
    trap - ERR INT TERM
    git commit -s -m "release: {{new}}"
    git tag -a "v{{new}}" -m "docket {{new}}"
    just publish "{{new}}"

# push a tag from `just release`; the Release workflow builds and publishes it
[group('release')]
publish new:
    #!/usr/bin/env bash
    set -euo pipefail
    # Separate from release so a failed push is one command to retry. The tag
    # push triggers .github/workflows/installer.yml, which tests, builds every
    # asset on a clean runner, and creates the GitHub release. docket update
    # reads releases/latest, so installed copies see the version only once
    # that workflow finishes.
    git rev-parse -q --verify "refs/tags/v{{new}}" >/dev/null \
      || { echo "no tag v{{new}}; run just release {{new}} first"; exit 1; }
    test "$(cat VERSION)" = "{{new}}" \
      || { echo "VERSION says $(cat VERSION), not {{new}}"; exit 1; }
    git push origin HEAD --follow-tags
    echo "pushed v{{new}}; the Release workflow publishes it"
    if command -v gh >/dev/null; then
      echo "watch it with: gh run watch \$(gh run list --workflow installer.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
    fi
    echo "published v{{new}}; docket update now offers it"
