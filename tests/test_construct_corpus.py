"""Replay against a real document corpus.

Skipped unless DOCKET_CORPUS names a checkout holding context/**/*.md. The
numbers in docs/superpowers/specs/2026-09-13-docket-construct-design.md were
measured this way, and this keeps them checkable.
"""

import os
import random
import re
import unittest
from pathlib import Path

from docket.construct import extract

CORPUS = os.environ.get("DOCKET_CORPUS", "")
_root = Path(CORPUS) if CORPUS else None
_have = bool(_root and (_root / "context").is_dir())


def _as_a_model_would(line: str) -> str:
    """A source line as extraction returns it: emphasis gone, respaced."""
    return re.sub(r"\s+", "  ", re.sub(r"[*_`]+", "", line)).strip()


@unittest.skipUnless(_have, "set DOCKET_CORPUS to a checkout with context/*.md")
class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = sorted(_root.rglob("context/**/*.md"))
        cls.git = extract.git_dates(_root)

    def test_one_git_call_covers_the_whole_tree(self):
        self.assertGreater(len(self.git), len(self.files))

    def test_nearly_every_document_resolves_a_date(self):
        dated = sum(
            1
            for f in self.files
            if extract.resolve_date(
                str(f.relative_to(_root)), f.read_text(errors="replace"), self.git
            )
        )
        # Measured at 96.5% over 372 documents. A drop means a date convention
        # changed, or the head window stopped covering where dates are written.
        self.assertGreaterEqual(dated / len(self.files), 0.90)

    def test_anchors_survive_the_formatting_a_model_strips(self):
        random.seed(20260914)
        hits = total = 0
        for f in random.sample(self.files, min(60, len(self.files))):
            text = f.read_text(errors="replace")
            lines = [l for l in text.splitlines() if len(l.strip()) > 30]
            for line in random.sample(lines, min(3, len(lines))):
                total += 1
                hits += bool(extract.anchor_line(_as_a_model_would(line), text))
        self.assertGreater(total, 100)
        # The spec's step-2 floor. Measured at 100% for these two perturbations;
        # real model output also paraphrases, which this cannot simulate.
        self.assertGreaterEqual(hits / total, 0.95)

    def test_an_anchor_does_not_match_a_different_document(self):
        random.seed(20260914)
        for _ in range(20):
            a, b = random.sample(self.files, 2)
            lines = [l for l in a.read_text(errors="replace").splitlines() if len(l.strip()) > 40]
            if not lines:
                continue
            probe = _as_a_model_would(random.choice(lines))
            self.assertIsNone(extract.anchor_line(probe, b.read_text(errors="replace")))


if __name__ == "__main__":
    unittest.main()
