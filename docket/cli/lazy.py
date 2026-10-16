"""Handlers and argument types that import their module on first call.

Building the parser must not import every subcommand's implementation: the
SessionStart hook builds it on every session to run `docket context`.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable


def lazy(module: str, name: str) -> Callable:
    def call(*args, **kwargs):
        return getattr(importlib.import_module(module), name)(*args, **kwargs)

    # argparse names a type function in its "invalid <name> value" error.
    call.__name__ = name
    return call
