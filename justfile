version := `cat VERSION 2>/dev/null || echo dev`
prefix := env_var_or_default("PREFIX", env_var("HOME") / ".local/bin")

# show available recipes
default:
    @just --list

# run both suites
[group('dev')]
test:
    python3 tests/test_docket.py
    python3 tests/test_install.py

# install and uninstall against a throwaway HOME, leaving this machine alone
[group('dev')]
verify:
    #!/usr/bin/env bash
    set -euo pipefail
    home=$(mktemp -d)
    trap 'rm -rf "$home"' EXIT
    HOME="$home" python3 install.py --yes
    "$home/.local/bin/docket" --version
    HOME="$home" python3 install.py --uninstall --yes
    for leftover in ".local/bin/docket" ".claude/skills/docket"; do
      if [ -e "$home/$leftover" ] || [ -L "$home/$leftover" ]; then
        echo "FAIL: uninstall left $leftover"
        exit 1
      fi
    done
    echo ok

# wire this machine
[group('install')]
install:
    python3 install.py

# print every file the installer would write, and write none of them
[group('install')]
dry:
    python3 install.py --dry-run

# remove what the installer wrote; keeps every ledger
[group('install')]
uninstall:
    python3 install.py --uninstall

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
