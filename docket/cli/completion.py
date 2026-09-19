"""The shell completion scripts docket prints for bash, zsh and fish.

Split from docket.cli.admin to keep that file under the 300 line limit. These
are three templates and one command that prints them; nothing here touches a
ledger.
"""

from __future__ import annotations

import argparse

from docket import features

_COMPLETION_FLAGS = (
    "--state",
    "--choice",
    "--alternative",
    "--scope",
    "--rationale",
    "--supports",
    "--depends-on",
    "--answers",
    "--supersedes",
    "--evidence",
    "--revisit",
    "--cost",
    "--pin",
    "--kind",
    "--query",
    "--file",
    "--max-chars",
    "--auto-scope",
    "--no-auto-scope",
    "--since",
    "--at",
    "--all",
    "--find",
    "--superseded",
    "--oneline",
    "--json",
    "--plain",
    "--pretty",
    "--style",
    "--interactive",
    "--no-interactive",
    "--for",
    "--version",
    "--dry-run",
    "--check",
)
_COMPLETION_CMDS = (
    "claim",
    "decision",
    "question",
    "list",
    "show",
    "graph",
    "context",
    "where",
    "check",
    "rebase",
    "migrate",
    "init",
    "feature",
    "completion",
    "update",
)
_COMPLETION_FEATURE_VERBS = (
    "start",
    "list",
    "show",
    "note",
    "amend",
    "done",
    "abandon",
    "brief",
    "remap",
    "gc",
)
_COMPLETION_FEATURE_FLAGS = (
    "--text",
    "--path",
    "--intends",
    "--status",
    "--include",
    "--exclude",
    "--clear",
    "--held",
    "--failed",
    "--state",
    "--expire",
    "--oneline",
    "--json",
)

# COMP_CWORD -gt 1 guards the branch: while the word "feature" is itself being
# completed, COMP_CWORD is 1 and COMP_WORDS[1] already holds it, so the branch
# ran and returned nothing, and the top-level command list never appeared.
_BASH_COMPLETION = f"""\
_docket() {{
    local cur prev
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    if [[ $COMP_CWORD -gt 1 && "${{COMP_WORDS[1]}}" == "feature" ]]; then
        if [[ "$cur" == -* ]]; then
            COMPREPLY=($(compgen -W "{" ".join(_COMPLETION_FEATURE_FLAGS)}" -- "$cur")); return
        fi
        case "$prev" in
            --state) COMPREPLY=($(compgen -W "active paused review done abandoned blocked" -- "$cur")); return ;;
            --status) COMPREPLY=($(compgen -W "{" ".join(features.STATUSES)}" -- "$cur")); return ;;
            --clear) COMPREPLY=($(compgen -W "{" ".join(features.CLEARABLE)}" -- "$cur")); return ;;
            --include|--exclude|--held|--failed)
                COMPREPLY=($(compgen -W "$(docket list --oneline 2>/dev/null | awk '{{print $1}}')" -- "$cur")); return ;;
            feature) COMPREPLY=($(compgen -W "{" ".join(_COMPLETION_FEATURE_VERBS)}" -- "$cur")); return ;;
        esac
        COMPREPLY=($(compgen -W "$(docket feature list --oneline 2>/dev/null | awk '{{print $2}}')" -- "$cur"))
        return
    fi
    case "$prev" in
        --state) COMPREPLY=($(compgen -W "unassessed accepted disputed rejected adopted revoked open resolved" -- "$cur")); return ;;
        --supports|--depends-on|--answers|--supersedes|show)
            COMPREPLY=($(compgen -W "$(docket list --oneline 2>/dev/null | awk '{{print $1}}')" -- "$cur")); return ;;
        completion) COMPREPLY=($(compgen -W "bash zsh fish" -- "$cur")); return ;;
    esac
    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "{" ".join(_COMPLETION_FLAGS)}" -- "$cur")); return
    fi
    COMPREPLY=($(compgen -W "{" ".join(_COMPLETION_CMDS)}" -- "$cur"))
}}
complete -F _docket docket
"""

_ZSH_COMPLETION = f"""\
#compdef docket

_docket_ids() {{
    local -a ids
    ids=(${{(f)"$(docket list --oneline 2>/dev/null | awk '{{print $1}}')"}})
    _describe 'id' ids
}}

_arguments -C \\
    '1: :({" ".join(_COMPLETION_CMDS)})' \\
    '*::arg:->args'

case $words[1] in
    show) _docket_ids ;;
    completion) _values 'shell' bash zsh fish ;;
    feature)
        case $words[2] in
            list) _arguments '--state[state]:state:(active paused review done abandoned)' '--oneline' '--json' ;;
            show) _arguments '--json' ;;
            amend) _arguments \\
                '--status[declared status]:status:({" ".join(features.STATUSES)})' \\
                '--path[declared path]:path:_files' \\
                '--intends[intended outcome]:text:' \\
                '--include[force a record in]:ids:' \\
                '--exclude[force a record out]:ids:' \\
                '--clear[empty a declared list]:field:({" ".join(features.CLEARABLE)})' ;;
            *) _values 'verb' {" ".join(_COMPLETION_FEATURE_VERBS)} ;;
        esac
        ;;
    claim|decision|question)
        _arguments \\
            '--state[state]:state:(unassessed accepted disputed rejected adopted revoked open resolved)' \\
            '--choice[decision choice]:choice:' \\
            '--alternative[decision alternative]:alternative:' \\
            '--supports[supporting ids]:id:_docket_ids' \\
            '--depends-on[decision prerequisites]:id:_docket_ids' \\
            '--answers[question ids]:id:_docket_ids' \\
            '--supersedes[retired ids]:id:_docket_ids' \\
            '--cost[cost if wrong]:cost:'
        ;;
esac
"""

_FISH_COMPLETION = f"""\
set -l docket_cmds {" ".join(_COMPLETION_CMDS)}
complete -c docket -n "not __fish_seen_subcommand_from $docket_cmds" -a "$docket_cmds"
complete -c docket -n "__fish_seen_subcommand_from show" -a "(docket list --oneline 2>/dev/null | awk '{{print \\$1}}')"
complete -c docket -n "__fish_seen_subcommand_from claim decision question" -l supports -a "(docket list --oneline 2>/dev/null | awk '{{print \\$1}}')"
complete -c docket -n "__fish_seen_subcommand_from claim decision question" -l supersedes -a "(docket list --oneline 2>/dev/null | awk '{{print \\$1}}')"
complete -c docket -n "__fish_seen_subcommand_from claim decision" -l state -a "unassessed accepted disputed rejected adopted revoked"
complete -c docket -n "__fish_seen_subcommand_from completion" -a "bash zsh fish"
"""

_COMPLETIONS = {"bash": _BASH_COMPLETION, "zsh": _ZSH_COMPLETION, "fish": _FISH_COMPLETION}


def cmd_completion(args: argparse.Namespace) -> int:
    print(_COMPLETIONS[args.shell], end="")
    return 0


__all__ = ["cmd_completion"]
