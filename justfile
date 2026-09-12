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

# refresh only the installed Docket checkout and graph viewer
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

# bump VERSION and both plugin manifests, test, commit and tag
[group('release')]
release new:
    #!/usr/bin/env bash
    set -euo pipefail
    test -z "$(git status --porcelain)" || { echo "working tree is dirty"; exit 1; }
    echo "{{new}}" > VERSION
    # Rewritten as JSON, not by sed: a manifest that stops parsing takes the
    # plugin down in every harness at once.
    for f in .claude-plugin/plugin.json .codex-plugin/plugin.json; do
      python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["version"]=sys.argv[2]; open(p,"w").write(json.dumps(d, indent=2)+"\n")' "$f" "{{new}}"
    done
    just test
    git add VERSION .claude-plugin/plugin.json .codex-plugin/plugin.json
    git commit -s -m "release: {{new}}"
    git tag -a "v{{new}}" -m "docket {{new}}"
    echo "tagged v{{new}}; push with: git push && git push --tags"
