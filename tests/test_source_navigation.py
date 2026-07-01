"""
End-to-end tests for reference-viewer match navigation.

Covers the ▶◀ / re-click navigation: stepping must move through match
*blocks* (not just pages), re-stamp the gold CURRENT_MATCH highlight on the
new block, and scroll the reference viewer to the block's position.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.main_window import MainWindow


SENTENCE_A = (
    "Quantum entanglement enables correlations between distant particles "
    "that classical physics cannot explain in any local realistic model."
)
SENTENCE_B = (
    "Photosynthesis converts sunlight carbon dioxide and water into glucose "
    "providing chemical energy for nearly all terrestrial ecosystems."
)


class TestSourceMatchNavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.ref_path = "tests/_nav_ref.pdf"
        cls.target_path = "tests/_nav_target.pdf"

        # Reference: sentence A on page 0, sentence B on page 2 — two match
        # blocks at clearly different reference positions.
        doc = fitz.open()
        doc.new_page().insert_text((50, 100), SENTENCE_A)
        doc.new_page().insert_text((50, 100), "Nothing relevant on this page.")
        doc.new_page().insert_text((50, 400), SENTENCE_B)
        doc.save(cls.ref_path)
        doc.close()

        # Target: both sentences, far apart, so they merge into separate blocks.
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), SENTENCE_A)
        filler = (
            "Meanwhile completely unrelated filler paragraphs discuss medieval "
            "castle architecture ramparts moats drawbridges towers battlements "
            "portcullises keeps garrisons siege engines trebuchets catapults "
            "armory blacksmith stables courtyards chapels dungeons cellars "
            "granaries watchtowers gatehouses barbicans curtains walls."
        )
        page.insert_text((50, 500), filler)
        page.insert_text((50, 700), SENTENCE_B)
        doc.save(cls.target_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        for p in (cls.ref_path, cls.target_path):
            if os.path.exists(p):
                os.remove(p)

    def setUp(self):
        self.window = MainWindow()
        self.window.chk_minimap.setChecked(False)
        self.window.show()
        QTest.qWait(50)

        comp = self.window.comparator
        comp.add_references([self.ref_path])
        results, _total, _stats = comp.compare_document(self.target_path)
        self.window.current_results = results
        self.window.current_target_file = self.target_path

        # Group result entries by match block
        self.entries_by_mid = {}
        for entries in results.values():
            for e in entries:
                self.entries_by_mid.setdefault(e.match_id, e)
        self.assertGreaterEqual(
            len(self.entries_by_mid), 2, "Test setup must produce >= 2 match blocks"
        )

    def tearDown(self):
        self.window.clear_results()
        self.window._bg_render_pool.waitForDone(5000)
        self.window.close()
        QTest.qWait(50)

    def _pages_with_current_match(self) -> set:
        return {
            lbl.page_index
            for lbl in self.window.source_view.slots
            if any(h.source == "CURRENT_MATCH" for h in lbl.highlights)
        }

    @staticmethod
    def _block_pages(block: dict) -> set:
        """Pages a block's reference rects live on (SW expansion may span two)."""
        return {rkey[0] for rkey in block["rect_keys"]}

    def _click_first_block(self):
        """Simulate clicking the block whose reference match is on page 0."""
        clicked = next(
            e for e in self.entries_by_mid.values() if e.source_data[0][0] == 0
        )
        self.window.current_match_list = [clicked]
        self.window.current_match_index = 0
        self.window.load_source_view(clicked.source, clicked.source_data)
        QTest.qWait(150)
        return clicked

    def test_click_marks_clicked_block_as_current(self):
        clicked = self._click_first_block()
        blocks = self.window._source_match_blocks

        self.assertGreaterEqual(len(blocks), 2)
        current = blocks[self.window._source_nav_index]
        self.assertEqual(current["match_id"], clicked.match_id)
        # Gold highlight must be exactly on the clicked block's pages
        self.assertIn(0, self._block_pages(current))
        self.assertEqual(self._pages_with_current_match(), self._block_pages(current))

    def test_next_match_moves_gold_highlight_and_scrolls(self):
        self._click_first_block()
        idx_before = self.window._source_nav_index

        self.window.next_match()
        QTest.qWait(50)

        blocks = self.window._source_match_blocks
        idx_after = self.window._source_nav_index
        self.assertNotEqual(idx_before, idx_after)

        # The gold highlight must have moved to the new current block's pages
        new_block = blocks[idx_after]
        self.assertEqual(self._pages_with_current_match(), self._block_pages(new_block))

        # The viewer must have scrolled to the new block's position
        expected_y = self.window._source_block_scroll_y(new_block)
        self.assertEqual(
            self.window.source_scroll.verticalScrollBar().value(), expected_y
        )

        # Counter reflects block-level navigation
        self.assertEqual(
            self.window.lbl_match_counter.text(),
            f"Match {idx_after + 1} of {len(blocks)}",
        )

    def test_reclick_cycles_phrase_occurrences(self):
        """Re-clicking the same target highlight must jump to the next
        reference occurrence of that phrase, not to an unrelated block."""
        ref_path = "tests/_nav_dup_ref.pdf"
        tgt_path = "tests/_nav_dup_target.pdf"

        # SENTENCE_A occurs twice in the reference (page 0 and page 2)
        doc = fitz.open()
        doc.new_page().insert_text((50, 100), SENTENCE_A)
        doc.new_page().insert_text((50, 100), "Nothing relevant on this page.")
        doc.new_page().insert_text((50, 400), SENTENCE_A)
        doc.save(ref_path)
        doc.close()

        doc = fitz.open()
        doc.new_page().insert_text((50, 100), SENTENCE_A)
        doc.save(tgt_path)
        doc.close()

        try:
            comp = self.window.comparator
            comp.add_references([ref_path])
            results, _t, _s = comp.compare_document(tgt_path)
            self.window.current_results = results
            self.window.current_target_file = tgt_path

            clicked = next(e for page in results.values() for e in page)
            self.window.handle_matches_clicked([clicked])
            QTest.qWait(150)

            occurrences = self.window._match_occurrences
            self.assertEqual(
                len(occurrences), 2, "Duplicated phrase must yield 2 occurrences"
            )
            self.assertEqual(self.window._occurrence_index, 0)
            primary_pages = {p for p, _, _ in occurrences[0]["source_data"]}
            alt_pages = {p for p, _, _ in occurrences[1]["source_data"]}
            self.assertNotEqual(primary_pages, alt_pages)

            # Re-click the exact same highlight → jump to the alternate occurrence
            self.window.handle_matches_clicked([clicked])
            QTest.qWait(150)
            self.assertEqual(self.window._occurrence_index, 1)
            self.assertEqual(self._pages_with_current_match(), alt_pages)

            # A third click wraps back to the primary occurrence
            self.window.handle_matches_clicked([clicked])
            QTest.qWait(150)
            self.assertEqual(self.window._occurrence_index, 0)
            self.assertEqual(self._pages_with_current_match(), primary_pages)
        finally:
            os.remove(ref_path)
            os.remove(tgt_path)

    def test_navigation_wraps_around(self):
        self._click_first_block()
        n = len(self.window._source_match_blocks)
        start = self.window._source_nav_index

        for _ in range(n):
            self.window.next_match()
        self.assertEqual(self.window._source_nav_index, start)
        # After a full cycle, the original block is current again
        block = self.window._source_match_blocks[start]
        self.assertEqual(self._pages_with_current_match(), self._block_pages(block))


if __name__ == "__main__":
    unittest.main()
