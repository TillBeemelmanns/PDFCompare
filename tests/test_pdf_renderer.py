import os
import sys
import unittest

import fitz

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.pdf_renderer import _page_pixel_size


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


if __name__ == "__main__":
    unittest.main()
