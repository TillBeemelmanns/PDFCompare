"""
Tests for the globally-ignored phrases feature.

Covers:
- _normalize_ignore_phrase: punctuation stripping + stopword removal
- load_ignored_phrases: reads file and normalizes each line
- compare_document: ignores blocks matching a phrase from the file
  - phrase without stopwords (auto-generated via right-click)
  - phrase with stopwords (manually written by the user)
"""

import os
import sys
import tempfile
import unittest

import fitz

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import compare_logic
from compare_logic import (
    PDFComparator,
    _normalize_ignore_phrase,
    load_ignored_phrases,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pdf(path: str, text: str) -> None:
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), text)
    doc.save(path)
    doc.close()


class TestNormalizeIgnorePhrase(unittest.TestCase):
    """Unit tests for the _normalize_ignore_phrase helper."""

    def test_strips_trailing_punctuation(self):
        self.assertEqual(_normalize_ignore_phrase("hello, world."), "hello world")

    def test_removes_stopwords(self):
        # "on", "and", "the" are stopwords
        result = _normalize_ignore_phrase(
            "International Conference on Robotics and Automation"
        )
        self.assertEqual(result, "international conference robotics automation")

    def test_no_stopwords_unchanged(self):
        result = _normalize_ignore_phrase("quick brown fox")
        self.assertEqual(result, "quick brown fox")

    def test_all_stopwords_returns_empty(self):
        result = _normalize_ignore_phrase("the and or but")
        self.assertEqual(result, "")

    def test_lowercases(self):
        result = _normalize_ignore_phrase("NEURAL NETWORKS")
        self.assertEqual(result, "neural networks")

    def test_mixed_punctuation(self):
        result = _normalize_ignore_phrase("deep learning, (transformers)")
        self.assertEqual(result, "deep learning transformers")


class TestLoadIgnoredPhrases(unittest.TestCase):
    """Unit tests for load_ignored_phrases reading and normalising the file."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        self._path = self._tmp.name
        self._orig_path = compare_logic._IGNORE_PHRASES_FILE
        # Redirect the module-level constant to our temp file
        compare_logic._IGNORE_PHRASES_FILE = type(self._orig_path)(self._path)

    def tearDown(self):
        compare_logic._IGNORE_PHRASES_FILE = self._orig_path
        os.unlink(self._path)

    def _write(self, lines):
        compare_logic._IGNORE_PHRASES_FILE.write_text(
            "\n".join(lines), encoding="utf-8"
        )

    def test_empty_file_returns_empty_frozenset(self):
        self._write([])
        self.assertEqual(load_ignored_phrases(), frozenset())

    def test_blank_lines_ignored(self):
        self._write(["", "   ", "quick brown fox", ""])
        result = load_ignored_phrases()
        self.assertIn("quick brown fox", result)
        self.assertEqual(len(result), 1)

    def test_stopwords_stripped_on_load(self):
        # User manually writes a natural-language phrase with stopwords
        self._write(["International Conference on Robotics and Automation"])
        result = load_ignored_phrases()
        # "on" and "and" must be removed so the phrase matches block_text
        self.assertIn("international conference robotics automation", result)
        self.assertNotIn("international conference on robotics and automation", result)

    def test_auto_generated_phrase_passes_through(self):
        # Auto-generated phrases (from right-click) have no stopwords already
        self._write(["quick brown fox"])
        result = load_ignored_phrases()
        self.assertIn("quick brown fox", result)

    def test_duplicates_collapsed(self):
        # "on" stripped → both lines normalise to the same string
        self._write(["quick brown fox", "quick brown fox"])
        result = load_ignored_phrases()
        self.assertEqual(len(result), 1)


class TestCompareDocumentIgnoresPhrases(unittest.TestCase):
    """Integration tests: compare_document must suppress ignored blocks.

    Each test uses a separate ref/target pair that contains exactly ONE matched
    phrase so that block-merging doesn't cause unrelated phrases to disappear.
    """

    @classmethod
    def setUpClass(cls):
        # Phrase A — no stopwords needed
        cls.ref_a = "tests/ignore_ref_a.pdf"
        cls.target_a = "tests/ignore_target_a.pdf"
        _make_pdf(cls.ref_a, "Neural networks achieve remarkable performance.")
        _make_pdf(cls.target_a, "Neural networks achieve remarkable performance.")

        # Phrase B — different vocabulary
        cls.ref_b = "tests/ignore_ref_b.pdf"
        cls.target_b = "tests/ignore_target_b.pdf"
        _make_pdf(cls.ref_b, "Deep learning transforms computer vision.")
        _make_pdf(cls.target_b, "Deep learning transforms computer vision.")

        # Combined target: both phrases present so we can verify independence.
        # We use *separate* reference PDFs (ref_a and ref_b) so the filler
        # words between the phrases don't match any reference and the merger
        # keeps phrase A and phrase B as distinct blocks.
        cls.target_ab = "tests/ignore_target_ab.pdf"
        _make_pdf(
            cls.target_ab,
            "Neural networks achieve remarkable performance. "
            "Deep learning transforms computer vision.",
        )

    @classmethod
    def tearDownClass(cls):
        for p in [
            cls.ref_a,
            cls.target_a,
            cls.ref_b,
            cls.target_b,
            cls.target_ab,
        ]:
            if os.path.exists(p):
                os.remove(p)

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        self._tmp.close()
        self._orig_path = compare_logic._IGNORE_PHRASES_FILE
        compare_logic._IGNORE_PHRASES_FILE = type(self._orig_path)(self._tmp.name)

    def tearDown(self):
        compare_logic._IGNORE_PHRASES_FILE = self._orig_path
        os.unlink(self._tmp.name)

    def _highlights_flat(self, results):
        words = []
        for hl_list in results.values():
            for h in hl_list:
                words.append(h.word.lower())
        return words

    def _write_ignore(self, *phrases):
        compare_logic._IGNORE_PHRASES_FILE.write_text(
            "\n".join(phrases) + "\n", encoding="utf-8"
        )

    def _comparator_for(self, ref_path):
        c = PDFComparator()
        c.add_references([ref_path])
        return c

    # ------------------------------------------------------------------
    # Baseline: phrases are detected when the ignore file is empty
    # ------------------------------------------------------------------

    def test_baseline_phrase_a_detected(self):
        c = self._comparator_for(self.ref_a)
        results, _, stats = c.compare_document(self.target_a)
        self.assertIn(
            self.ref_a, stats, "Phrase A should be detected with no ignore rules"
        )

    def test_baseline_phrase_b_detected(self):
        c = self._comparator_for(self.ref_b)
        results, _, stats = c.compare_document(self.target_b)
        self.assertIn(
            self.ref_b, stats, "Phrase B should be detected with no ignore rules"
        )

    # ------------------------------------------------------------------
    # Ignore phrase A (exact match — as auto-generated by right-click)
    # ------------------------------------------------------------------

    def test_ignore_phrase_exact_suppresses_match(self):
        self._write_ignore("neural networks achieve remarkable performance")
        c = self._comparator_for(self.ref_a)
        results, _, stats = c.compare_document(self.target_a)
        self.assertNotIn(
            self.ref_a,
            stats,
            "Block must be suppressed when its phrase is in the ignore list",
        )

    def test_ignore_phrase_exact_does_not_affect_unrelated(self):
        self._write_ignore("neural networks achieve remarkable performance")
        c = self._comparator_for(self.ref_b)
        results, _, stats = c.compare_document(self.target_b)
        self.assertIn(
            self.ref_b,
            stats,
            "Phrase B must not be affected by ignoring phrase A",
        )

    # ------------------------------------------------------------------
    # Ignore phrase A typed manually — including stopwords in the middle
    # Stopword "and" gets stripped → normalises to the same form as phrase A
    # ------------------------------------------------------------------

    def test_ignore_phrase_with_stopword_suppresses_match(self):
        # "and" is a stopword → stripped during normalisation
        self._write_ignore("neural networks and achieve remarkable performance")
        c = self._comparator_for(self.ref_a)
        results, _, stats = c.compare_document(self.target_a)
        self.assertNotIn(
            self.ref_a,
            stats,
            "Phrase with an embedded stopword must normalise and still suppress the block",
        )

    # ------------------------------------------------------------------
    # Ignore phrase B
    # ------------------------------------------------------------------

    def test_ignore_phrase_b_suppresses_match(self):
        self._write_ignore("deep learning transforms computer vision")
        c = self._comparator_for(self.ref_b)
        results, _, stats = c.compare_document(self.target_b)
        self.assertNotIn(self.ref_b, stats, "Phrase B should be suppressed")

    # ------------------------------------------------------------------
    # Combined target: ignoring one phrase must not affect the other block
    # (only possible when the phrases form separate blocks)
    # ------------------------------------------------------------------

    def _comparator_ab(self):
        """Comparator with both phrase-A and phrase-B references loaded separately.

        Using two distinct reference files ensures the filler text between
        the phrases in target_ab doesn't appear in either reference, so the
        merger keeps the two match blocks separate.
        """
        c = PDFComparator()
        c.add_references([self.ref_a, self.ref_b])
        return c

    def test_ignore_phrase_a_leaves_phrase_b_in_combined(self):
        self._write_ignore("neural networks achieve remarkable performance")
        c = self._comparator_ab()
        results, _, _ = c.compare_document(self.target_ab)
        words = self._highlights_flat(results)
        self.assertFalse(
            any("neural" in w for w in words),
            "Phrase A should be suppressed",
        )
        self.assertTrue(
            any("deep" in w or "learning" in w for w in words),
            "Phrase B must remain visible when only phrase A is ignored",
        )

    def test_ignore_phrase_b_leaves_phrase_a_in_combined(self):
        self._write_ignore("deep learning transforms computer vision")
        c = self._comparator_ab()
        results, _, _ = c.compare_document(self.target_ab)
        words = self._highlights_flat(results)
        self.assertFalse(
            any("deep" in w for w in words),
            "Phrase B should be suppressed",
        )
        self.assertTrue(
            any("neural" in w or "networks" in w for w in words),
            "Phrase A must remain visible when only phrase B is ignored",
        )


if __name__ == "__main__":
    unittest.main()
