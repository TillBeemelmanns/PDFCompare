"""
Tests for the HighlightEntry dataclass and highlight pipeline.

Covers:
- HighlightEntry construction, defaults, and mutability
- Consistency between compare_document output and HighlightEntry
- Reference-viewer highlight building (current vs other, rect dedup, copy safety)
"""

import unittest
import os
import sys

import fitz

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models import HighlightEntry
from compare_logic import PDFComparator


class TestHighlightEntryDefaults(unittest.TestCase):
    """Verify that HighlightEntry has safe defaults for all optional fields."""

    def test_minimal_construction(self):
        """Only rect is truly required; everything else has a default."""
        h = HighlightEntry(rect=fitz.Rect(0, 0, 10, 10))
        self.assertEqual(h.source, "")
        self.assertAlmostEqual(h.confidence, 0.7)
        self.assertIsNone(h.source_data)
        self.assertIsNone(h.match_id)
        self.assertAlmostEqual(h.match_density, 0.0)
        self.assertEqual(h.word, "")
        self.assertFalse(h.ignored)
        self.assertIsNone(h.preview_source)

    def test_full_construction(self):
        """All fields can be set explicitly."""
        data = [(0, fitz.Rect(1, 2, 3, 4), "hello")]
        h = HighlightEntry(
            rect=fitz.Rect(10, 20, 30, 40),
            source="/path/to/ref.pdf",
            confidence=0.95,
            source_data=data,
            match_id=42,
            match_density=0.8,
            word="example",
            ignored=False,
            preview_source="/path/to/target.pdf",
        )
        self.assertEqual(h.source, "/path/to/ref.pdf")
        self.assertEqual(h.match_id, 42)
        self.assertAlmostEqual(h.confidence, 0.95)
        self.assertEqual(h.word, "example")
        self.assertEqual(h.preview_source, "/path/to/target.pdf")
        self.assertEqual(len(h.source_data), 1)

    def test_ignored_is_mutable(self):
        """The ignored flag must be settable after construction (ignore_match)."""
        h = HighlightEntry(rect=fitz.Rect(0, 0, 10, 10))
        self.assertFalse(h.ignored)
        h.ignored = True
        self.assertTrue(h.ignored)

    def test_rect_is_accessible(self):
        """rect coordinates are directly accessible as attributes."""
        r = fitz.Rect(5, 10, 50, 100)
        h = HighlightEntry(rect=r)
        self.assertAlmostEqual(h.rect.x0, 5)
        self.assertAlmostEqual(h.rect.y0, 10)
        self.assertAlmostEqual(h.rect.x1, 50)
        self.assertAlmostEqual(h.rect.y1, 100)


class TestHighlightEntryFromCompareDocument(unittest.TestCase):
    """Verify compare_document returns HighlightEntry objects."""

    @classmethod
    def setUpClass(cls):
        cls.ref_path = "tests/_hl_ref.pdf"
        cls.target_path = "tests/_hl_target.pdf"

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(
            (50, 50),
            "The quick brown fox jumps over the lazy dog in the garden.",
        )
        doc.save(cls.ref_path)
        doc.close()

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(
            (50, 50),
            "I noticed that the quick brown fox jumps over the lazy dog today.",
        )
        doc.save(cls.target_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        for p in [cls.ref_path, cls.target_path]:
            if os.path.exists(p):
                os.remove(p)

    def test_results_are_highlight_entries(self):
        """Every element in compare_document results must be a HighlightEntry."""
        comp = PDFComparator()
        comp.add_references([self.ref_path])
        results, total, stats = comp.compare_document(self.target_path)

        self.assertGreater(len(results), 0, "Expected at least one page with matches")
        for page_idx, entries in results.items():
            for entry in entries:
                self.assertIsInstance(entry, HighlightEntry)

    def test_result_entries_have_required_fields(self):
        """Each result entry must have non-empty source, source_data, and match_id."""
        comp = PDFComparator()
        comp.add_references([self.ref_path])
        results, total, stats = comp.compare_document(self.target_path)

        for page_idx, entries in results.items():
            for entry in entries:
                self.assertTrue(entry.source, "source must be a non-empty string")
                self.assertIsNotNone(entry.source_data, "source_data must not be None")
                self.assertIsNotNone(entry.match_id, "match_id must not be None")
                self.assertGreater(entry.confidence, 0.0)
                self.assertIsInstance(entry.rect, fitz.Rect)

    def test_result_entries_have_word(self):
        """Each result entry should carry the target-side word text."""
        comp = PDFComparator()
        comp.add_references([self.ref_path])
        results, total, stats = comp.compare_document(self.target_path)

        words_found = []
        for entries in results.values():
            for entry in entries:
                if entry.word:
                    words_found.append(entry.word.lower())
        self.assertGreater(len(words_found), 0, "Expected words in result entries")

    def test_source_data_format(self):
        """source_data must contain (page_idx, rect, word) triples.

        Reference-side rects are plain (x0, y0, x1, y1) tuples.
        """
        comp = PDFComparator()
        comp.add_references([self.ref_path])
        results, total, stats = comp.compare_document(self.target_path)

        for entries in results.values():
            for entry in entries:
                if entry.source_data:
                    for triple in entry.source_data:
                        self.assertEqual(len(triple), 3)
                        page, rect, word = triple
                        self.assertIsInstance(page, int)
                        self.assertIsInstance(rect, tuple)
                        self.assertEqual(len(rect), 4)
                        self.assertIsInstance(word, str)


class TestReferenceViewerHighlightPipeline(unittest.TestCase):
    """Test the highlight building logic used by load_source_view.

    Extracted as pure functions to avoid needing a Qt event loop.
    """

    def _build_current_rect_keys(self, source_data):
        """Reproduce the current_rect_keys building from load_source_view."""
        keys = set()
        for ref_page, ref_rect, _ in source_data:
            keys.add((ref_page, *ref_rect))
        return keys

    def _collect_and_classify(self, current_results, file_path, current_rect_keys):
        """Reproduce the two-phase rect collection + classification."""
        seen_rect_keys = set()
        all_rect_objects = {}
        rkeys_by_page = {}
        target_data_by_ref_rect = {}

        for target_page_idx, page_highlights in current_results.items():
            for h in page_highlights:
                if h.source != file_path or h.ignored:
                    continue
                target_triple = (target_page_idx, h.rect, h.word)
                for ref_page, ref_rect, _ in h.source_data or []:
                    rkey = (ref_page, *ref_rect)
                    target_data_by_ref_rect.setdefault(rkey, []).append(target_triple)
                    if rkey in seen_rect_keys:
                        continue
                    seen_rect_keys.add(rkey)
                    all_rect_objects[rkey] = fitz.Rect(ref_rect)
                    rkeys_by_page.setdefault(ref_page, []).append(rkey)

        all_highlights_by_page = {}
        for ref_page, rkeys in rkeys_by_page.items():
            all_highlights_by_page[ref_page] = [
                (all_rect_objects[rkey], rkey in current_rect_keys) for rkey in rkeys
            ]
        return all_highlights_by_page, target_data_by_ref_rect

    def test_current_match_marked_correctly(self):
        """Rects from the clicked match must be marked is_current=True."""
        ref_rect_a = (10, 20, 100, 30)
        ref_rect_b = (10, 40, 100, 50)

        source_data_a = [(0, ref_rect_a, "word_a")]
        source_data_b = [(0, ref_rect_b, "word_b")]

        current_results = {
            0: [
                HighlightEntry(
                    rect=fitz.Rect(5, 5, 50, 15),
                    source="/ref.pdf",
                    source_data=source_data_a,
                    match_id=1,
                    word="target_a",
                ),
                HighlightEntry(
                    rect=fitz.Rect(5, 20, 50, 30),
                    source="/ref.pdf",
                    source_data=source_data_b,
                    match_id=2,
                    word="target_b",
                ),
            ]
        }

        # User clicked match A
        current_rect_keys = self._build_current_rect_keys(source_data_a)
        highlights, _ = self._collect_and_classify(
            current_results, "/ref.pdf", current_rect_keys
        )

        self.assertIn(0, highlights)
        rects_and_flags = highlights[0]
        # Should have 2 rects: A=current, B=other
        self.assertEqual(len(rects_and_flags), 2)

        for rect, is_current in rects_and_flags:
            rkey = (0, rect.x0, rect.y0, rect.x1, rect.y1)
            if rkey == (0, *ref_rect_a):
                self.assertTrue(is_current, "Match A should be current")
            else:
                self.assertFalse(is_current, "Match B should be other")

    def test_order_independence(self):
        """is_current must not depend on which page is processed first."""
        shared_rect = (10, 20, 100, 30)

        source_data_current = [(0, shared_rect, "shared")]
        source_data_other = [(0, shared_rect, "shared")]

        # Other match is on page 0 (processed first), current on page 5
        current_results = {
            0: [
                HighlightEntry(
                    rect=fitz.Rect(5, 5, 50, 15),
                    source="/ref.pdf",
                    source_data=source_data_other,
                    match_id=99,
                    word="other_word",
                ),
            ],
            5: [
                HighlightEntry(
                    rect=fitz.Rect(5, 50, 50, 60),
                    source="/ref.pdf",
                    source_data=source_data_current,
                    match_id=100,
                    word="current_word",
                ),
            ],
        }

        # User clicked the match on page 5 (current)
        current_rect_keys = self._build_current_rect_keys(source_data_current)
        highlights, _ = self._collect_and_classify(
            current_results, "/ref.pdf", current_rect_keys
        )

        # The shared rect must be marked as current regardless of iteration order
        self.assertIn(0, highlights)
        for rect, is_current in highlights[0]:
            self.assertTrue(
                is_current,
                "Shared rect must be current (the clicked match references it)",
            )

    def test_ignored_matches_excluded(self):
        """Ignored highlights must not contribute rects to the reference view."""
        ref_rect = (10, 20, 100, 30)
        source_data = [(0, ref_rect, "word")]

        current_results = {
            0: [
                HighlightEntry(
                    rect=fitz.Rect(5, 5, 50, 15),
                    source="/ref.pdf",
                    source_data=source_data,
                    match_id=1,
                    word="visible",
                ),
                HighlightEntry(
                    rect=fitz.Rect(5, 20, 50, 30),
                    source="/ref.pdf",
                    source_data=[(0, (10, 50, 100, 60), "hidden")],
                    match_id=2,
                    word="ignored_word",
                    ignored=True,
                ),
            ]
        }

        current_rect_keys = self._build_current_rect_keys(source_data)
        highlights, _ = self._collect_and_classify(
            current_results, "/ref.pdf", current_rect_keys
        )

        # Only the non-ignored match's ref rect should appear
        total_rects = sum(len(v) for v in highlights.values())
        self.assertEqual(total_rects, 1, "Only the non-ignored rect should appear")

    def test_target_data_collected(self):
        """target_data_by_ref_rect must map ref rkeys to target triples."""
        ref_rect = (10, 20, 100, 30)
        target_rect = fitz.Rect(5, 5, 50, 15)
        source_data = [(0, ref_rect, "ref_word")]

        current_results = {
            3: [
                HighlightEntry(
                    rect=target_rect,
                    source="/ref.pdf",
                    source_data=source_data,
                    match_id=1,
                    word="target_word",
                ),
            ]
        }

        current_rect_keys = self._build_current_rect_keys(source_data)
        _, target_data = self._collect_and_classify(
            current_results, "/ref.pdf", current_rect_keys
        )

        rkey = (0, *ref_rect)
        self.assertIn(rkey, target_data)
        triples = target_data[rkey]
        self.assertEqual(len(triples), 1)
        page_idx, rect, word = triples[0]
        self.assertEqual(page_idx, 3)
        self.assertEqual(word, "target_word")

    def test_different_source_files_excluded(self):
        """Highlights from a different source file must not appear."""
        ref_rect = (10, 20, 100, 30)

        current_results = {
            0: [
                HighlightEntry(
                    rect=fitz.Rect(5, 5, 50, 15),
                    source="/ref.pdf",
                    source_data=[(0, ref_rect, "match")],
                    match_id=1,
                    word="word",
                ),
                HighlightEntry(
                    rect=fitz.Rect(5, 20, 50, 30),
                    source="/other_ref.pdf",
                    source_data=[(0, (10, 50, 100, 60), "other")],
                    match_id=2,
                    word="other",
                ),
            ]
        }

        current_rect_keys = self._build_current_rect_keys([(0, ref_rect, "match")])
        highlights, _ = self._collect_and_classify(
            current_results, "/ref.pdf", current_rect_keys
        )

        total_rects = sum(len(v) for v in highlights.values())
        self.assertEqual(total_rects, 1, "Only /ref.pdf rects should appear")


class TestRectCopySafety(unittest.TestCase):
    """Verify that merge operations don't corrupt shared rect data."""

    def test_merge_rects_copy(self):
        """fitz.Rect(r) must produce an independent copy."""
        original = fitz.Rect(10, 20, 50, 30)
        copy = fitz.Rect(original)

        # Mutate the copy
        copy.x1 = 200

        # Original must be unchanged
        self.assertAlmostEqual(original.x1, 50)
        self.assertAlmostEqual(copy.x1, 200)


if __name__ == "__main__":
    unittest.main()
