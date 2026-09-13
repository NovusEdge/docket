"""The provider boundary. No network: the SDK is never imported here."""

import unittest

from docket.construct import client


class ConfigTests(unittest.TestCase):
    def test_reads_the_openrouter_key_from_the_environment(self):
        cfg = client.config({"OPENROUTER_API_KEY": "sk-or-x"})
        self.assertEqual(cfg["api_key"], "sk-or-x")
        self.assertIn("openrouter.ai", cfg["base_url"])

    def test_refuses_to_run_without_a_key(self):
        with self.assertRaises(client.ClientError) as caught:
            client.config({})
        # The message has to name the variable; an operator running a one-time
        # bootstrap has no other clue what is missing.
        self.assertIn("OPENROUTER_API_KEY", str(caught.exception))

    def test_a_model_can_be_overridden(self):
        self.assertEqual(client.config({"OPENROUTER_API_KEY": "k",
                                        "DOCKET_CONSTRUCT_MODEL": "x/y"})["model"],
                         "x/y")

    def test_has_a_default_model(self):
        self.assertTrue(client.config({"OPENROUTER_API_KEY": "k"})["model"])


class RequestTests(unittest.TestCase):
    SCHEMA = {"type": "object", "properties": {"records": {"type": "array"}},
              "required": ["records"]}

    def test_routes_only_to_providers_that_honour_the_schema(self):
        # OpenRouter enforces json_schema per endpoint, not per model, and some
        # providers silently fall back to json_object (c83).
        body = client.request("prompt", self.SCHEMA, model="x/y")
        self.assertIs(body["extra_body"]["provider"]["require_parameters"], True)

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


class ParseTests(unittest.TestCase):
    SCHEMA = {"type": "object", "properties": {"records": {"type": "array"}},
              "required": ["records"]}

    def test_returns_the_parsed_object(self):
        self.assertEqual(client.parse('{"records": [1]}', self.SCHEMA),
                         {"records": [1]})

    def test_rejects_a_response_that_is_not_json(self):
        # The silent json_object fallback looks exactly like this.
        with self.assertRaises(client.SchemaViolation):
            client.parse("Here are the records you asked for.", self.SCHEMA)

    def test_rejects_json_missing_a_required_key(self):
        with self.assertRaises(client.SchemaViolation):
            client.parse('{"other": []}', self.SCHEMA)

    def test_rejects_a_json_array_where_an_object_was_required(self):
        with self.assertRaises(client.SchemaViolation):
            client.parse('[1, 2]', self.SCHEMA)

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
