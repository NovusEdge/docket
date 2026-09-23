#!/usr/bin/env python3
"""Rewrite this project's question-shaped decision headlines as statements.

81 decisions were recorded with the question they settled as text and the
answer in choice. The write-time refusal stops new ones; this rewrites the
existing text in place after writing a backup beside the ledger. Ids,
relations, choice, and provenance stay untouched.

Superseding each record instead would retire all 81, and 36 records declare
support or prerequisites through them, so every one of those would lose its
grounds.

One-off, for this repository. The headlines were drafted per record and
reviewed by hand; nothing here generalises into a docket subcommand.

Run from the repository root:

    python3 scripts/declarative_ledger.py --dry-run
    python3 scripts/declarative_ledger.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docket.ledger import _normalized, _reject_question_text  # noqa: E402

LEDGER = Path(".docket/ledger.jsonl")
BACKUP = Path(".docket/ledger-predeclarative-backup.jsonl")

HEADLINES = {
    "d2": "An outcome is a change that persists after the chain ends: a world change or an epistemic one.",
    "d12": "The ledger lives at ~/.claude/docket keyed by git root, overridable by a project .docket or the DOCKET_HOME/CLAUDE_CONFIG_DIR variables.",
    "d13": "Docket captures session, author, and branch provenance fields from the start, before anything else consumes them.",
    "d14": "Docket ships plugin config for Codex only and documents copyable config for the other harnesses.",
    "d16": "Docket tracks open defects as GitHub issues on NovusEdge/docket, leaving decisions to the ledger.",
    "d21": "Docket documentation follows de-slopify and ASD-STE100 Issue 9, keeping the public README free of internal detail.",
    "d22": "Users install docket through a single stdlib-only install.py at the repo root, serving both curl-pipe and checkout runs.",
    "d23": "The installer wires Claude Code by merging a SessionStart hook and installing the skill, skipping this when the marketplace plugin is already present.",
    "d24": "The installer writes harness config user-globally by default, with a --project flag to target the current repository instead.",
    "d25": "Users update docket by re-running the idempotent installer, which pulls the existing checkout with git pull --ff-only.",
    "d26": "The installer separates plan generation from execution, returning Action records that a single apply() writes, so --dry-run and tests stay pure.",
    "d27": "On Windows, docket.cmd and docket.ps1 shims invoke a resolved absolute interpreter path, and PATH edits go through SetEnvironmentVariable rather than setx.",
    "d28": "The installer wires Claude Code by linking the checkout into ~/.claude/skills/docket as a plugin, with no settings.json merge or marker file.",
    "d29": "The installer edits Windows PATH directly through stdlib winreg on the registry, then broadcasts WM_SETTINGCHANGE, avoiding percent-variable expansion.",
    "d30": "The installer configures Codex by shelling out to codex plugin marketplace add and codex plugin add docket@NovusEdge, verified end to end.",
    "d33": "A wrong justification is corrected by superseding the entry with a restatement, deferring a dedicated amend event to stage 3 retraction.",
    "d34": "The native installer engine and UI move to Go under installer/, using Bubble Tea, Bubbles, and Lip Gloss, while the ledger CLI stays Python.",
    "d35": "The native installer edits Windows PATH using Go's golang.org/x/sys/windows/registry, preserving REG_SZ/REG_EXPAND_SZ and keeping the docket.cmd shim.",
    "d36": "Docket browses the decision graph by default through a native Bubble Tea and Bubbles viewer, falling back to static output for pipes.",
    "d37": "Docket ships installer integrations for Claude Code, Codex, Gemini CLI, Cursor, GitHub Copilot CLI, and OpenCode.",
    "d38": "installer/install.py remains Docket's stable entry point, running or building the Go installer depending on whether it is inside a source checkout.",
    "d39": "The installer places harness configuration user-globally by default, and --project moves the Claude skill and Cursor rule into the current repository.",
    "d40": "Users update Docket with the installer --update option, which keeps harness and PATH configuration.",
    "d41": "The native installer separates BuildPlan and PreparePlan from ExecutePlan and represents operations as Action values, so dry runs and tests stay isolated.",
    "d42": "The native installer lets the Codex CLI own plugin registration through codex plugin marketplace add and codex plugin add, without hand-editing config.",
    "d43": "Docket merges PR #5 and reconciles the project ledger before exploring richer decision metadata and agent context delivery on a separate branch.",
    "d44": "The typed ledger redesign may break the current format, and existing history migrates explicitly.",
    "d45": "Docket 0.8.0 adopts a typed record and context model with claims, decisions, and questions.",
    "d46": "Docket requires Python 3.11 or later.",
    "d53": "Docket resolves ledger conflicts by computing the grounded extension of a bipolar argumentation framework.",
    "d54": "The storage layout stays independent of the chosen topology.",
    "d55": "A topology change touches only the resolver's cascade edge kinds and winner ordering, not the algorithm.",
    "d56": "Docket replaces the flat supports list with a capped set of alternative justification sets.",
    "d57": "Docket caches the grounded extension and causal attribution under the ledger revision hash to keep briefings cheap.",
    "d63": "The first topology change renders the full transitive supersede chain on the heading record.",
    "d64": "Design specs stay untracked in the gitignored docs/superpowers/ directory, while decisions live in the ledger.",
    "d65": "Docket's support field already stores alternative justification sets, leaving only the cardinality cap open.",
    "d66": "Docket warns that archival is due once the ledger reaches 10000 records.",
    "d67": "No topology ships, and Docket sets no per-project default topology.",
    "d68": "The first topology change renders the full transitive supersede chain on the heading record.",
    "d69": "No topology ships, and Docket sets no per-project default topology.",
    "d70": "Docket bounds label growth by subsumption, keeping a cardinality cap only as a backstop.",
    "d71": "Docket commits the project ledger only at a release, as a snapshot beside the version bump.",
    "d72": "Published docs stay flat in docs/ and map onto one GitBook space through gitbook-docs.yaml.",
    "d73": "Published docs lead with plain declarative task guides and keep reference material on separate pages.",
    "d74": "User-facing documentation uses simple declarative English and task-based guides, checked against source.",
    "d76": "Installation docs lead with a pasteable setup prompt that points agents to docs/agent-setup.md.",
    "d77": "Docket provides a docket update subcommand that picks the update path from the install shape.",
    "d78": "A session hook prints an update notice from a cached release tag without an inline network request.",
    "d79": "lib/ becomes a contained docket package with relative imports and a split CLI.",
    "d80": "bin/docket stays a Python script with a shebang instead of a Go launcher binary.",
    "d81": "The installer writes the OpenCode plugin as a single file at ~/.config/opencode/plugins/docket.ts.",
    "d82": "lib/ becomes the docket package, and every import in it is absolute.",
    "d84": "Docket construct depends on the official openai SDK pointed at OpenRouter's endpoint, imported lazily.",
    "d87": "Docket ships the package refactor and the construct command in 0.12.0.",
    "d88": "installer/install.py stays Docket's stable installation entry point.",
    "d89": "A wrong justification is corrected by superseding the entry with a restatement.",
    "d91": "Docket rejects echo-form alternatives and rationales but only hints at empty reasoning fields.",
    "d92": "Docket documentation follows de-slopify and ASD-STE100 principles and keeps the README free of internal details.",
    "d93": "Docket rejects echo-form alternatives and rationales but only hints at empty reasoning fields.",
    "d94": "Justification represents alternatives as a list of support sets, and any surviving set keeps the claim alive.",
    "d95": "Docket drops subsumed support sets and caps each surviving label at a fixed number of sets.",
    "d96": "Docket sets no record-count trigger for archival but fixes the archive mechanism now.",
    "d97": "planOpenCode writes the OpenCode plugin to plugins/docket.ts for automatic discovery.",
    "d98": "Selection adds a contradiction closure, so a record enters the briefing with the records that oppose it.",
    "d102": "Docket ships one selection arrangement, chain collapse, with no per-project topology setting.",
    "d106": "Docket ships no topology built-ins and no per-project setting for the selector.",
    "d107": "Work in flight is tracked in a separate append-only store, features.jsonl, apart from the ledger.",
    "d108": "Feature records use a monotonic f-prefixed integer id, qualified by a base SHA only when ambiguous.",
    "d109": "A feature's blocked state derives from the ledger's prerequisite relation on its attached decisions.",
    "d110": "A feature's change set comes from a first-parent git log diff against the merge base with the default branch.",
    "d113": "Feature briefs keep ranking ledger records by literal-prefix specificity.",
    "d114": "The 8000-character budget bounds the text a reader scans at session start and no longer claims to proxy tokens.",
    "d115": "docket graph --format mermaid prints the decision graph as a mermaid flowchart to stdout.",
    "d116": "Docket emits both mermaid and graphviz DOT as graph export formats, defaulting to mermaid.",
    "d117": "An amend event clears a declared list through a separate cleared field, applied before field assignments.",
    "d118": "scope_strength in docket/context.py stays the single path matcher used by classify and expand.",
    "d119": "Docket modules follow one responsibility per file with a 300-line ceiling, so large modules get split.",
    "d120": "just release runs roll_changelog.py first and refuses to release with an empty Unreleased section.",
    "d121": "docket graph --format csv writes nodes.csv and edges.csv for Gephi-style import.",
    "d122": "Feature-tracking guidance lives in its own docket-feature skill, separate from the main docket skill.",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print the changes and write nothing"
    )
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args(argv)

    if not args.ledger.exists():
        print(f"declarative: {args.ledger} does not exist", file=sys.stderr)
        return 1

    lines = args.ledger.read_text().splitlines()
    out: list[str] = []
    changed = 0
    for line in lines:
        entry = json.loads(line)
        new = HEADLINES.get(entry["id"])
        if new is None or entry["text"] == new:
            out.append(line)
            continue
        if entry["kind"] != "decision":
            print(f"declarative: {entry['id']} is a {entry['kind']}", file=sys.stderr)
            return 1
        entry["text"] = new
        _reject_question_text(entry)
        # _reject_empty_reasoning also checks alternatives, and records written
        # before that rule repeat the choice there. Only the text checks apply.
        text = _normalized(new)
        if text in (_normalized(entry["choice"]), _normalized(entry.get("rationale", ""))):
            print(f"declarative: {entry['id']} headline restates a field", file=sys.stderr)
            return 1
        changed += 1
        print(f"{entry['id']:5} {new}")
        out.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))

    missed = sorted(
        (entry["id"] for entry in map(json.loads, out)
         if entry["kind"] == "decision" and entry["text"].rstrip().endswith("?")),
        key=lambda ident: int(ident[1:]),
    )
    if missed:
        print(f"\nstill question-shaped: {', '.join(missed)}")

    if not changed:
        print("declarative: nothing to change")
        return 0
    if args.dry_run:
        print(f"\ndeclarative: {changed} records would change; wrote nothing")
        return 0

    shutil.copy2(args.ledger, BACKUP)
    args.ledger.write_text("\n".join(out) + "\n")
    print(f"\ndeclarative: rewrote {changed} records; backup at {BACKUP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
