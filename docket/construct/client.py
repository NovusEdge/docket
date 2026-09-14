"""The provider boundary: what construct sends, and what it accepts back.

Nothing here imports an SDK. Building a request and checking a response are
pure, so both are testable without a key and without a network. The one
function that talks to a provider imports its SDK inside its own body, which is
what keeps the SessionStart hook free of the dependency.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, TypedDict

from docket.env import project_root

SCHEMA_NAME = "docket_construct"


class Provider(TypedDict):
    """One provider's fixed shape. `base_url` is None where the SDK knows it."""

    env: str
    sdk: str
    base_url: str | None
    model: str


# OpenRouter is the documented default: one key reaches every provider through
# one endpoint. Gemini and OpenAI serve OpenAI-compatible endpoints, so the same
# SDK reaches them with only the base URL changed.
#
# Anthropic is the exception, and `sdk` is what records it. Anthropic's
# OpenAI-compatible layer ignores `response_format` outright, so a Claude key
# reached that way returns prose and every parse() fails. Its own SDK carries
# the schema in `output_config`, which is why this one entry names a different
# package and a different request shape.
PROVIDERS: dict[str, Provider] = {
    "openrouter": {
        "env": "OPENROUTER_API_KEY",
        "sdk": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "google/gemini-3.8-flash",
    },
    "gemini": {
        "env": "GEMINI_API_KEY",
        "sdk": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.8-flash",
    },
    "openai": {
        "env": "OPENAI_API_KEY",
        "sdk": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.6-luna",
    },
    "anthropic": {
        "env": "ANTHROPIC_API_KEY",
        "sdk": "anthropic",
        "base_url": None,
        "model": "claude-haiku-4-5-20251001",
    },
}
BASE_URL = PROVIDERS["openrouter"]["base_url"]
DEFAULT_MODEL = PROVIDERS["openrouter"]["model"]

# Anthropic requires max_tokens. Extraction returns every record in one
# document and linking returns links for a batch of 120, so a small ceiling
# truncates the JSON and parse() reports a syntax error rather than the cause.
MAX_TOKENS = 16384

MAX_BACKOFF = 60.0
_BASE_BACKOFF = 1.5


class ClientError(RuntimeError):
    """Construct cannot reach a provider at all."""


class SchemaViolation(ValueError):
    """A response that did not conform to the schema it was asked for."""


def dotenv_key(root: Path, name: str) -> str | None:
    """One key read out of `root/.env`, or None.

    A lookup, never a loader. A .env holds every secret a project has, and
    loading it wholesale would put database passwords and signing keys into the
    process for the sake of one API key. Nothing here touches os.environ.
    """
    path = root / ".env"
    try:
        body = path.read_text(errors="replace")
    except OSError:
        return None

    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#"):
            continue
        # `export FOO=bar` is as common in a .env as `FOO=bar`, because the same
        # file gets sourced by a shell.
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        field, sep, value = line.partition("=")
        if sep and field.strip() == name:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value or None
    return None


def config(env: Mapping[str, str] | None = None, root: Path | None = None) -> dict:
    """Where to call and as whom, from the environment or the project's .env.

    The first provider whose key is present wins, so OpenRouter stays the
    default when several are set. DOCKET_CONSTRUCT_PROVIDER names one instead,
    which is the only way out for someone holding three keys who wants the
    third. An exported variable beats the file: a .env is a project default, and
    an export is the operator naming a key for this run.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    root = project_root() if root is None else root

    wanted = source.get("DOCKET_CONSTRUCT_PROVIDER", "")
    if wanted and wanted not in PROVIDERS:
        raise ClientError(
            f"DOCKET_CONSTRUCT_PROVIDER names {wanted!r}, which is not one of: "
            f"{', '.join(PROVIDERS)}."
        )
    candidates = {wanted: PROVIDERS[wanted]} if wanted else PROVIDERS

    for name, spec in candidates.items():
        key = source.get(spec["env"], "") or dotenv_key(root, spec["env"]) or ""
        if key:
            return {
                "provider": name,
                "sdk": spec["sdk"],
                "api_key": key,
                "base_url": source.get("DOCKET_CONSTRUCT_BASE_URL", spec["base_url"]),
                "model": source.get("DOCKET_CONSTRUCT_MODEL", spec["model"]),
            }

    names = " or ".join(spec["env"] for spec in candidates.values())
    raise ClientError(
        f"docket construct needs {names}, in the environment or in "
        f"{root / '.env'}. An OpenRouter key reaches every provider through "
        "one endpoint; the others reach their own provider only."
    )


def request(prompt: str, schema: dict, model: str, provider: str = "openrouter") -> dict:
    """The request body for one extraction or linking call.

    On OpenRouter, `require_parameters` is the part that matters. OpenRouter
    honours `json_schema` per endpoint rather than per model, so the same model
    reached through a different upstream provider may ignore the schema and fall
    back to plain JSON. The flag routes only to providers that support it, and
    `parse` still checks, because the flag is not a guarantee.

    A single-provider endpoint has nothing to route, so it gets no such field.

    Anthropic takes a different body: its own Messages API carries the schema in
    `output_config` and requires `max_tokens`.
    """
    if provider == "anthropic":
        return {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {
                "format": {"type": "json_schema", "schema": schema},
            },
        }

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": schema},
        },
    }
    if provider == "openrouter":
        body["extra_body"] = {"provider": {"require_parameters": True}}
    return body


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}


def parse(text: str, schema: dict) -> dict:
    """The response as an object, or a violation naming what was wrong.

    Deliberately shallow: it checks what a silent fallback breaks, which is the
    top-level shape and the required keys. A provider that ignored the schema
    returns prose or a differently shaped object, and both fail here.
    """
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaViolation(f"response is not JSON: {exc}") from None

    expected = _TYPES.get(schema.get("type", "object"), dict)
    if not isinstance(value, expected):
        raise SchemaViolation(f"response is {type(value).__name__}, expected {schema.get('type')}")

    # A second binding, because _TYPES holds runtime types. The isinstance above
    # narrows `value` to the whole union those types span, and every key lookup
    # below then reads as an index into an int.
    body: Any = value
    properties = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in body:
            raise SchemaViolation(f"response is missing required key {name!r}")
        want = _TYPES.get(properties.get(name, {}).get("type"))
        if want and not isinstance(body[name], want):
            raise SchemaViolation(
                f"key {name!r} is {type(body[name]).__name__}, expected {properties[name]['type']}"
            )
    return body


def backoff(attempt: int, retry_after: str | None = None) -> float:
    """Seconds to wait before retrying, honouring Retry-After when given.

    The extraction pass issues one call per document across a thread pool, so a
    429 is expected rather than exceptional.
    """
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return min(_BASE_BACKOFF * (2**attempt), MAX_BACKOFF)
