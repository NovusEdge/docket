import tempfile
import unittest
from pathlib import Path

from lib.docket_config import DEFAULTS, ConfigError, load, merge


def write(directory, text):
    (Path(directory) / "config.toml").write_text(text, encoding="utf-8")


class ConfigTests(unittest.TestCase):
    def test_absent_file_yields_defaults(self):
        with tempfile.TemporaryDirectory() as home:
            settings, identity = load(home)
        self.assertEqual(settings, DEFAULTS)
        self.assertEqual(identity, "default")

    def test_override_replaces_one_value_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as home:
            write(home, "[budget]\ntarget = 12000\n")
            settings, identity = load(home)
        self.assertEqual(settings["budget"]["target"], 12000)
        self.assertEqual(settings["budget"]["outer_multiple"],
                         DEFAULTS["budget"]["outer_multiple"])
        self.assertEqual(settings["weights"], DEFAULTS["weights"])
        self.assertNotEqual(identity, "default")

    def test_identity_is_stable_for_the_same_settings(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            write(first, "[weights]\ntext = 300\n")
            write(second, "[weights]\ntext = 300\n")
            self.assertEqual(load(first)[1], load(second)[1])

    def test_a_file_restating_the_defaults_stays_default(self):
        with tempfile.TemporaryDirectory() as home:
            write(home, f"[budget]\ntarget = {DEFAULTS['budget']['target']}\n")
            self.assertEqual(load(home)[1], "default")

    def test_the_example_file_states_the_defaults(self):
        import tomllib
        example = Path(__file__).resolve().parent.parent / "docs" / "config.example.toml"
        # Every value in the example is documented as the default. A drifting
        # example teaches a wrong number and silently changes a tuned briefing.
        self.assertEqual(merge(tomllib.loads(example.read_text(encoding="utf-8"))),
                         DEFAULTS)

    def test_unknown_section_and_key_are_rejected(self):
        with self.assertRaises(ConfigError):
            merge({"nonsense": {"x": 1}})
        with self.assertRaises(ConfigError):
            merge({"weights": {"nonsense": 1}})

    def test_non_integer_values_are_rejected(self):
        for value in ("1000", 1000.5, True, None):
            with self.assertRaises(ConfigError):
                merge({"weights": {"text": value}})

    def test_incoherent_combinations_are_rejected(self):
        with self.assertRaises(ConfigError):
            merge({"budget": {"target": 100}})
        with self.assertRaises(ConfigError):
            merge({"budget": {"outer_multiple": 0}})
        with self.assertRaises(ConfigError):
            merge({"index": {"detail_min": 200}})
        with self.assertRaises(ConfigError):
            merge({"expansion": {"decay_denominator": 0}})
        with self.assertRaises(ConfigError):
            merge({"auto_scope": {"limit": 0}})

    def test_malformed_toml_is_rejected(self):
        with tempfile.TemporaryDirectory() as home:
            write(home, "[budget\ntarget = 9000\n")
            with self.assertRaises(ConfigError):
                load(home)

    def test_settings_change_the_briefing_and_the_header(self):
        from lib.docket_context import build_context
        from tests.test_context import entry, projected

        records = [
            entry("d1", "decision", "Installer decision", choice="x", scope=("installer/**",)),
            entry("d2", "decision", "Renderer decision", choice="y", scope=("lib/**",)),
        ]
        history = projected(records)
        tuned = merge({"weights": {"scope_glob": 10}})
        plain = build_context(history, files=("lib/render.py",), ledger="repo")
        changed = build_context(history, files=("lib/render.py",), ledger="repo",
                                settings=tuned, settings_id="abcd1234")
        self.assertIn("scope=700", plain)
        self.assertIn("scope=10", changed)
        self.assertIn("| settings: abcd1234", changed)
        self.assertNotIn("settings:", plain)


if __name__ == "__main__":
    unittest.main()
