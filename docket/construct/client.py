"""The provider boundary: what construct sends, and what it accepts back.

Nothing here imports the SDK. Building a request and checking a response are
pure, so both are testable without a key and without a network. The one
function that talks to OpenRouter imports `openai` inside its own body, which
is what keeps the SessionStart hook free of the dependency.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from docket.env import project_root

SCHEMA_NAME = "docket_construct"

# OpenRouter is the documented default: one key reaches every provider through
# one endpoint. Gemini serves an OpenAI-compatible endpoint of its own, so the
# same SDK reaches it with only the base URL changed, which is the path for
# someone who already holds a Gemini key.
PROVIDERS = {
    "openrouter": {
        "env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "google/gemini-3.8-flash",
    },
    "gemini": {
        "env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.8-flash",
    },
}
BASE_URL = PROVIDERS["openrouter"]["base_url"]
DEFAULT_MODEL = PROVIDERS["openrouter"]["model"]

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
            line = line[len("export "):].lstrip()
        field, sep, value = line.partition("=")
        if sep and field.strip() == name:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value or None
    return None


def config(env: dict[str, str] | None = None, root: Path | None = None) -> dict:
    """Where to call and as whom, from the environment or the project's .env.

    The first provider whose key is present wins, so OpenRouter stays the
    default when both are set. An exported variable beats the file: a .env is a
    project default, and an export is the operator naming a key for this run.
    """
    env = os.environ if env is None else env
    root = project_root() if root is None else root
    for name, spec in PROVIDERS.items():
        key = env.get(spec["env"], "") or dotenv_key(root, spec["env"]) or ""
        if key:
            return {
                "provider": name,
                "api_key": key,
                "base_url": env.get("DOCKET_CONSTRUCT_BASE_URL", spec["base_url"]),
                "model": env.get("DOCKET_CONSTRUCT_MODEL", spec["model"]),
            }
    wanted = " or ".join(spec["env"] for spec in PROVIDERS.values())
    raise ClientError(
        f"docket construct needs {wanted}, in the environment or in "
        f"{root / '.env'}. An OpenRouter key reaches every provider through "
        "one endpoint; a Gemini key reaches Gemini.")


def request(prompt: str, schema: dict, model: str,
            provider: str = "openrouter") -> dict:
    """The request body for one extraction or linking call.

    On OpenRouter, `require_parameters` is the part that matters. OpenRouter
    honours `json_schema` per endpoint rather than per model, so the same model
    reached through a different upstream provider may ignore the schema and fall
    back to plain JSON. The flag routes only to providers that support it, and
    `parse` still checks, because the flag is not a guarantee.

    A single-provider endpoint has nothing to route, so it gets no such field.
    """
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
    "object": dict, "array": list, "string": str,
    "number": (int, float), "integer": int, "boolean": bool,
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
        raise SchemaViolation(
            f"response is {type(value).__name__}, expected {schema.get('type')}")

    properties = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in value:
            raise SchemaViolation(f"response is missing required key {name!r}")
        want = _TYPES.get(properties.get(name, {}).get("type"))
        if want and not isinstance(value[name], want):
            raise SchemaViolation(
                f"key {name!r} is {type(value[name]).__name__}, expected "
                f"{properties[name]['type']}")
    return value


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
    return min(_BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
