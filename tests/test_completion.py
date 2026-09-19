import shlex
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from docket.cli.completion import _BASH_COMPLETION


@unittest.skipUnless(shutil.which("bash"), "bash is not installed")
class BashCompletionTests(unittest.TestCase):
    def complete(self, words, cword):
        """What _docket offers, given the words typed and the cursor position."""

        quoted = " ".join(shlex.quote(word) for word in words)
        program = (
            f"{_BASH_COMPLETION}\n"
            f"COMP_WORDS=({quoted})\n"
            f"COMP_CWORD={cword}\n"
            "_docket\n"
            'printf "%s\\n" "${COMPREPLY[@]}"\n'
        )
        result = subprocess.run(
            ["bash", "--norc", "--noprofile", "-c", program],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return [line for line in result.stdout.splitlines() if line]

    def test_the_word_feature_still_completes_at_the_top_level(self):
        # COMP_WORDS[1] already holds the word being completed, so the feature
        # branch ran while the cursor was still on it and returned nothing.
        self.assertIn("feature", self.complete(["docket", "feature"], 1))
        self.assertIn("feature", self.complete(["docket", "feat"], 1))

    def test_a_verb_follows_the_feature_word(self):
        offered = self.complete(["docket", "feature", ""], 2)
        self.assertIn("start", offered)
        self.assertIn("gc", offered)

    def test_a_flag_completes_inside_the_feature_group(self):
        offered = self.complete(["docket", "feature", "amend", "--"], 3)
        self.assertIn("--clear", offered)
        self.assertIn("--include", offered)

    def test_clear_offers_the_clearable_fields(self):
        self.assertEqual(
            sorted(self.complete(["docket", "feature", "amend", "one", "--clear", ""], 5)),
            ["exclude", "include", "intends"],
        )

    def test_state_offers_the_projected_state_too(self):
        offered = self.complete(["docket", "feature", "list", "--state", ""], 4)
        self.assertIn("blocked", offered)
        self.assertIn("active", offered)

    def test_the_top_level_commands_still_complete(self):
        offered = self.complete(["docket", ""], 1)
        self.assertIn("check", offered)
        self.assertIn("feature", offered)


if __name__ == "__main__":
    unittest.main()
