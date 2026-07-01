import os
import sys
import unittest

import fitz

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.pdf_renderer import _page_pixel_size, PixmapCache


class TestPagePixelSize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf_path = "tests/_renderer_dims.pdf"

        doc = fitz.open()
        first = doc.new_page()
        first.insert_text((50, 50), "Renderer sizing regression test.")
        second = doc.new_page(width=612, height=792)
        second.insert_text((50, 50), "Different page size for coverage.")
        doc.save(cls.pdf_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)

    def test_page_pixel_size_matches_rasterized_pixmap(self):
        doc = fitz.open(self.pdf_path)
        zoom = 1.2
        zoom_key = round(zoom, 2)

        try:
            for page in doc:
                dims = _page_pixel_size(page, zoom)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom_key, zoom_key))
                self.assertEqual(dims, (pix.width, pix.height))
        finally:
            doc.close()

    def test_page_pixel_size_rounds_zoom_consistently(self):
        doc = fitz.open(self.pdf_path)
        try:
            page = doc[0]
            self.assertEqual(
                _page_pixel_size(page, 1.2000000000000002),
                _page_pixel_size(page, 1.2),
            )
        finally:
            doc.close()


class TestPixmapCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication(sys.argv)

    def _pixmap(self, w: int, h: int):
        from PyQt6.QtGui import QPixmap

        pm = QPixmap(w, h)
        pm.fill()
        return pm

    def test_put_replaces_existing_entry(self):
        cache = PixmapCache()
        key = ("f.pdf", 0, 1.0)
        cache.put(key, self._pixmap(10, 10))
        replacement = self._pixmap(20, 20)
        cache.put(key, replacement)

        self.assertEqual(len(cache), 1)
        self.assertEqual(cache.get(key).width(), 20)
        self.assertEqual(cache.used_bytes, 20 * 20 * 4)

    def test_lru_eviction_respects_byte_budget(self):
        cache = PixmapCache(max_bytes=2 * 10 * 10 * 4)
        cache.put(("f.pdf", 0, 1.0), self._pixmap(10, 10))
        cache.put(("f.pdf", 1, 1.0), self._pixmap(10, 10))
        cache.get(("f.pdf", 0, 1.0))  # promote page 0 to MRU
        cache.put(("f.pdf", 2, 1.0), self._pixmap(10, 10))

        self.assertIsNone(cache.get(("f.pdf", 1, 1.0)))  # LRU evicted
        self.assertIsNotNone(cache.get(("f.pdf", 0, 1.0)))
        self.assertIsNotNone(cache.get(("f.pdf", 2, 1.0)))
        self.assertEqual(cache.used_bytes, 2 * 10 * 10 * 4)


if __name__ == "__main__":
    unittest.main()
