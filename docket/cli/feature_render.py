"""Rendering for the feature brief command."""

from __future__ import annotations

import sys

from docket import env, feature_project, features


def cmd_feature_brief(args) -> int:
    from docket import feature_brief, ledger

    path = env.features_path()
    root = env.project_root()
    current = feature_project.project(features.read(path))
    if args.name:
        feature = feature_project.resolve(current, args.name)
    else:
        branch = env.branch(root)
        open_now = [f for f in current if f["state"] not in features.TERMINAL_STATES]
        on_branch = [f for f in open_now if f["branch"] == branch] if branch else []
        candidates = on_branch or open_now
        if not candidates:
            print(
                "docket: no active feature; name one or run 'docket feature start'",
                file=sys.stderr,
            )
            return 1
        feature = candidates[-1]

    entries = ledger.project(ledger.read(env.ledger_path()), validated=True)
    files = feature_brief.expand(root, feature["paths"])
    attached = feature_brief.attach(
        entries, files, include=feature["include"], exclude=feature["exclude"]
    )
    print(feature_brief.render(feature, attached, limit_chars=feature_brief.budget_share()))
    return 0


__all__ = ["cmd_feature_brief"]
