"""The provider boundary. No network: the SDK is never imported here."""

import os
import tempfile
import unittest
from pathlib import Path

from docket.construct import client


class DotenvTests(unittest.TestCase):
    """Only the keys construct asks for, and never into the environment.

    A .env holds every secret a project has. Loading the file wholesale would
    put database passwords and signing keys into the process for the sake of
    one API key.
    """

    def env(self, body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".env").write_text(body)
        return root

    def test_reads_a_named_key(self):
        root = self.env("OPENROUTER_API_KEY=sk-or-x\n")
        self.assertEqual(client.dotenv_key(root, "OPENROUTER_API_KEY"), "sk-or-x")

    def test_ignores_every_other_key(self):
        root = self.env("DATABASE_URL=postgres://u:p@h/db\nOPENROUTER_API_KEY=k\n")
        self.assertIsNone(client.dotenv_key(root, "GEMINI_API_KEY"))
        self.assertNotIn("DATABASE_URL", os.environ)

    def test_strips_quotes(self):
        root = self.env('OPENROUTER_API_KEY="sk-or-x"\n')
        self.assertEqual(client.dotenv_key(root, "OPENROUTER_API_KEY"), "sk-or-x")

    def test_strips_an_export_prefix(self):
        root = self.env("export OPENROUTER_API_KEY=sk-or-x\n")
        self.assertEqual(client.dotenv_key(root, "OPENROUTER_API_KEY"), "sk-or-x")

    def test_skips_a_comment(self):
        root = self.env("# OPENROUTER_API_KEY=old\nOPENROUTER_API_KEY=new\n")
        self.assertEqual(client.dotenv_key(root, "OPENROUTER_API_KEY"), "new")

    def test_returns_none_for_an_empty_value(self):
        root = self.env("OPENROUTER_API_KEY=\n")
        self.assertIsNone(client.dotenv_key(root, "OPENROUTER_API_KEY"))

    def test_returns_none_when_there_is_no_file(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.assertIsNone(client.dotenv_key(Path(tmp.name), "OPENROUTER_API_KEY"))

    def test_a_real_environment_variable_wins(self):
        # A .env is a project default. An exported variable is the operator
        # saying which key to use for this run.
        root = self.env("OPENROUTER_API_KEY=from-file\n")
        cfg = client.config({"OPENROUTER_API_KEY": "from-shell"}, root=root)
        self.assertEqual(cfg["api_key"], "from-shell")

    def test_config_falls_back_to_the_file(self):
        root = self.env("OPENROUTER_API_KEY=from-file\n")
        self.assertEqual(client.config({}, root=root)["api_key"], "from-file")

    def test_config_names_the_file_it_searched(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(client.ClientError) as caught:
            client.config({}, root=Path(tmp.name))
        self.assertIn(".env", str(caught.exception))


class ConfigTests(unittest.TestCase):
    def test_reads_the_openrouter_key_from_the_environment(self):
        cfg = client.config({"OPENROUTER_API_KEY": "sk-or-x"})
        self.assertEqual(cfg["api_key"], "sk-or-x")
        self.assertIn("openrouter.ai", cfg["base_url"])

    def test_refuses_to_run_without_a_key(self):
        with self.assertRaises(client.ClientError) as caught:
            client.config({})
        # The message has to name the variables; an operator running a one-time
        # bootstrap has no other clue what is missing.
        for spec in client.PROVIDERS.values():
            self.assertIn(spec["env"], str(caught.exception))

    def test_a_model_can_be_overridden(self):
        self.assertEqual(
            client.config({"OPENROUTER_API_KEY": "k", "DOCKET_CONSTRUCT_MODEL": "x/y"})["model"],
            "x/y",
        )

    def test_has_a_default_model(self):
        self.assertTrue(client.config({"OPENROUTER_API_KEY": "k"})["model"])

    def test_falls_back_to_a_gemini_key(self):
        # Gemini serves an OpenAI-compatible endpoint, so the same SDK reaches
        # it with only the base URL changed.
        cfg = client.config({"GEMINI_API_KEY": "AQ.x"})
        self.assertEqual(cfg["api_key"], "AQ.x")
        self.assertIn("generativelanguage.googleapis.com", cfg["base_url"])
        self.assertEqual(cfg["provider"], "gemini")

    def test_a_gemini_model_carries_no_provider_prefix(self):
        # OpenRouter names it google/gemini-...; Gemini's own endpoint does not.
        self.assertNotIn("/", client.config({"GEMINI_API_KEY": "k"})["model"])

    def test_openrouter_wins_when_both_keys_are_present(self):
        cfg = client.config({"OPENROUTER_API_KEY": "a", "GEMINI_API_KEY": "b"})
        self.assertEqual(cfg["provider"], "openrouter")

    def test_falls_back_to_an_openai_key(self):
        cfg = client.config({"OPENAI_API_KEY": "sk-x"})
        self.assertEqual(cfg["provider"], "openai")
        self.assertIn("api.openai.com", cfg["base_url"])
        self.assertEqual(cfg["sdk"], "openai")

    def test_an_anthropic_key_selects_the_anthropic_sdk(self):
        # Anthropic's OpenAI-compatible layer ignores response_format, so a
        # Claude key reached through the openai SDK returns prose.
        cfg = client.config({"ANTHROPIC_API_KEY": "sk-ant-x"})
        self.assertEqual(cfg["provider"], "anthropic")
        self.assertEqual(cfg["sdk"], "anthropic")
        self.assertIsNone(cfg["base_url"])

    def test_every_other_provider_uses_the_openai_sdk(self):
        for name in ("openrouter", "gemini", "openai"):
            self.assertEqual(client.PROVIDERS[name]["sdk"], "openai")

    def test_a_named_provider_beats_the_order(self):
        # Someone holding three keys has no other way to reach the third.
        cfg = client.config(
            {
                "OPENROUTER_API_KEY": "a",
                "ANTHROPIC_API_KEY": "b",
                "DOCKET_CONSTRUCT_PROVIDER": "anthropic",
            }
        )
        self.assertEqual(cfg["provider"], "anthropic")

    def test_a_named_provider_reports_only_its_own_key(self):
        with self.assertRaises(client.ClientError) as caught:
            client.config(
                {"OPENROUTER_API_KEY": "a", "DOCKET_CONSTRUCT_PROVIDER": "anthropic"},
                root=Path("/nonexistent"),
            )
        self.assertIn("ANTHROPIC_API_KEY", str(caught.exception))
        self.assertNotIn("OPENROUTER_API_KEY", str(caught.exception))

    def test_an_unknown_provider_name_is_refused(self):
        with self.assertRaises(client.ClientError) as caught:
            client.config({"DOCKET_CONSTRUCT_PROVIDER": "grok"})
        self.assertIn("grok", str(caught.exception))


class RequestTests(unittest.TestCase):
    SCHEMA = {
        "type": "object",
        "properties": {"records": {"type": "array"}},
        "required": ["records"],
    }

    def test_routes_only_to_providers_that_honour_the_schema(self):
        # OpenRouter enforces json_schema per endpoint, not per model, and some
        # providers silently fall back to json_object (c83).
        body = client.request("prompt", self.SCHEMA, model="x/y")
        self.assertIs(body["extra_body"]["provider"]["require_parameters"], True)

    def test_sends_no_routing_hint_to_a_single_provider(self):
        # require_parameters is OpenRouter's own field. Gemini's endpoint has
        # one provider, so there is nothing to route and nothing to ask for.
        body = client.request("prompt", self.SCHEMA, model="gemini-3.8-flash", provider="gemini")
        self.assertNotIn("extra_body", body)

    def test_asks_for_the_schema_by_name_and_strictly(self):
        body = client.request("prompt", self.SCHEMA, model="x/y")
        fmt = body["response_format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertTrue(fmt["json_schema"]["name"])
        self.assertIs(fmt["json_schema"]["strict"], True)
        self.assertEqual(fmt["json_schema"]["schema"], self.SCHEMA)

    def test_sends_the_prompt_as_the_only_user_message(self):
        body = client.request("extract this", self.SCHEMA, model="x/y")
        self.assertEqual([m["role"] for m in body["messages"]], ["user"])
        self.assertEqual(body["messages"][0]["content"], "extract this")

    def test_anthropic_carries_the_schema_in_output_config(self):
        # The Messages API has no response_format. Sending one would reach
        # Anthropic as an unknown field and the schema would go unasked for.
        body = client.request("prompt", self.SCHEMA, model="claude-haiku-4-5", provider="anthropic")
        self.assertNotIn("response_format", body)
        fmt = body["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["schema"], self.SCHEMA)

    def test_anthropic_sets_max_tokens(self):
        # Required by the Messages API. A short ceiling truncates the JSON and
        # parse() then reports a syntax error rather than the cause.
        body = client.request("prompt", self.SCHEMA, model="claude-haiku-4-5", provider="anthropic")
        self.assertEqual(body["max_tokens"], client.MAX_TOKENS)

    def test_anthropic_gets_no_openrouter_routing_hint(self):
        body = client.request("prompt", self.SCHEMA, model="claude-haiku-4-5", provider="anthropic")
        self.assertNotIn("extra_body", body)


class ParseTests(unittest.TestCase):
    SCHEMA = {
        "type": "object",
        "properties": {"records": {"type": "array"}},
        "required": ["records"],
    }

    def test_returns_the_parsed_object(self):
        self.assertEqual(client.parse('{"records": [1]}', self.SCHEMA), {"records": [1]})

    def test_rejects_a_response_that_is_not_json(self):
        # The silent json_object fallback looks exactly like this.
        with self.assertRaises(client.SchemaViolation):
            client.parse("Here are the records you asked for.", self.SCHEMA)

    def test_rejects_json_missing_a_required_key(self):
        with self.assertRaises(client.SchemaViolation):
            client.parse('{"other": []}', self.SCHEMA)

    def test_rejects_a_json_array_where_an_object_was_required(self):
        with self.assertRaises(client.SchemaViolation):
            client.parse("[1, 2]", self.SCHEMA)

    def test_rejects_a_required_key_of_the_wrong_type(self):
        with self.assertRaises(client.SchemaViolation):
            client.parse('{"records": "not a list"}', self.SCHEMA)


class BackoffTests(unittest.TestCase):
    def test_waits_longer_after_each_attempt(self):
        delays = [client.backoff(n) for n in range(4)]
        self.assertEqual(delays, sorted(delays))
        self.assertLess(delays[0], delays[-1])

    def test_honours_a_retry_after_header(self):
        self.assertEqual(client.backoff(0, retry_after="12"), 12.0)

    def test_ignores_an_unparseable_retry_after(self):
        self.assertEqual(client.backoff(0, retry_after="whenever"), client.backoff(0))

    def test_caps_the_wait(self):
        self.assertLessEqual(client.backoff(50), client.MAX_BACKOFF)


if __name__ == "__main__":
    unittest.main()
