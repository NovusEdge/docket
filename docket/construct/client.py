"""The provider boundary: what construct sends, and what it accepts back.

Nothing here imports the SDK. Building a request and checking a response are
pure, so both are testable without a key and without a network. The one
function that talks to OpenRouter imports `openai` inside its own body, which
is what keeps the SessionStart hook free of the dependency.
"""

from __future__ import annotations

import json
import os

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.8-flash"
SCHEMA_NAME = "docket_construct"

MAX_BACKOFF = 60.0
_BASE_BACKOFF = 1.5


class ClientError(RuntimeError):
    """Construct cannot reach a provider at all."""


class SchemaViolation(ValueError):
    """A response that did not conform to the schema it was asked for."""


def config(env: dict[str, str] | None = None) -> dict:
    """Where to call and as whom, from the environment."""
    env = os.environ if env is None else env
    key = env.get("OPENROUTER_API_KEY", "")
    if not key:
        raise ClientError(
            "docket construct needs OPENROUTER_API_KEY. One key reaches every "
            "provider through one endpoint; see docs for the other paths.")
    return {
        "api_key": key,
        "base_url": env.get("OPENROUTER_BASE_URL", BASE_URL),
        "model": env.get("DOCKET_CONSTRUCT_MODEL", DEFAULT_MODEL),
    }


def request(prompt: str, schema: dict, model: str) -> dict:
    """The request body for one extraction or linking call.

    `require_parameters` is the part that matters. OpenRouter honours
    `json_schema` per endpoint rather than per model, so the same model reached
    through a different upstream provider may ignore the schema and fall back
    to plain JSON. The flag routes only to providers that support it; `parse`
    still checks, because the flag is not a guarantee.
    """
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": schema},
        },
        "extra_body": {"provider": {"require_parameters": True}},
    }


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
