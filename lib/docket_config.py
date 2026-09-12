"""Tunable renderer settings, read from a TOML file beside the ledger.

Every value is an integer. The renderer's ordering is reproducible only while
its inputs are known, so a briefing prints the fingerprint of the settings that
produced it whenever they differ from the defaults.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any


CONFIG_NAME = "config.toml"

DEFAULTS: dict[str, dict[str, int]] = {
    "budget": {
        "target": 8000,
        # A task-matching record may push the briefing past the target, up to
        # this multiple of it. Dropping a record the caller asked for defeats
        # the briefing; growing without bound defeats the context window.
        "outer_multiple": 3,
        "minimum": 512,
    },
    "index": {
        "detail_min": 40,
        "detail_max": 140,
        # Most records the index names. Beyond this it prints a count and points
        # at `docket list`, because several hundred identifiers are not
        # something an agent can act on. Measured in experiments/context-scale:
        # the admission gate prices the index at one bare identifier per record,
        # so each index line adds about 40 characters past budget.target. At 40
        # lines a thousand-record ledger renders 9,500 characters; at 120 it
        # renders 12,400.
        "max_lines": 40,
    },
    "weights": {
        "scope_exact": 1000,
        "scope_glob": 700,
        "scope_prefix": 500,
        # Above scope_exact. Only an explicit --query reaches this component, and
        # a query states the task, while a file scope taken from the working
        # tree only guesses at it.
        "text": 1100,
        "recency": 200,
        "degree": 50,
        "degree_cap": 10,
        "pinned": 400,
    },
    "expansion": {
        "decay_numerator": 1,
        "decay_denominator": 2,
        "floor": 50,
    },
    "auto_scope": {
        "limit": 50,
    },
}


class ConfigError(ValueError):
    """A settings file that cannot be used as written."""


def _fingerprint(settings: Mapping[str, Any]) -> str:
    if settings == DEFAULTS:
        return "default"
    canonical = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]


def merge(overrides: Mapping[str, Any] | None) -> dict[str, dict[str, int]]:
    """Apply overrides onto the defaults, rejecting anything unrecognised.

    An unknown key is an error, not a silent no-op: a typo in a settings file
    would otherwise leave the writer believing a value took effect.
    """

    settings = {section: dict(values) for section, values in DEFAULTS.items()}
    for section, values in (overrides or {}).items():
        if section not in settings:
            raise ConfigError(f"unknown settings section [{section}]")
        if not isinstance(values, Mapping):
            raise ConfigError(f"[{section}] must be a table")
        for key, value in values.items():
            if key not in settings[section]:
                raise ConfigError(f"unknown setting {section}.{key}")
            if type(value) is not int:
                raise ConfigError(f"{section}.{key} must be an integer")
            settings[section][key] = value

    budget = settings["budget"]
    if budget["target"] < budget["minimum"]:
        raise ConfigError("budget.target must be at least budget.minimum")
    if budget["outer_multiple"] < 1:
        raise ConfigError("budget.outer_multiple must be at least 1")
    if settings["index"]["detail_min"] > settings["index"]["detail_max"]:
        raise ConfigError("index.detail_min must not exceed index.detail_max")
    if settings["index"]["max_lines"] < 1:
        raise ConfigError("index.max_lines must be at least 1")
    if settings["expansion"]["decay_denominator"] < 1:
        raise ConfigError("expansion.decay_denominator must be at least 1")
    if settings["auto_scope"]["limit"] < 1:
        raise ConfigError("auto_scope.limit must be at least 1")
    return settings


def load(directory: Path | str | None) -> tuple[dict[str, dict[str, int]], str]:
    """Read settings from ``directory/config.toml``, falling back to defaults."""

    if directory is None:
        return merge(None), "default"
    path = Path(directory) / CONFIG_NAME
    if not path.is_file():
        return merge(None), "default"
    try:
        overrides = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    settings = merge(overrides)
    return settings, _fingerprint(settings)


__all__ = ["CONFIG_NAME", "DEFAULTS", "ConfigError", "load", "merge"]
