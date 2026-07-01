"""
Tests for UI state behavior: Run-button gating, file-list display,
and the status-bar zoom indicator.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.main_window import MainWindow
from gui.widgets import FileListWidget


class TestFileListDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_additem_shows_basename_keeps_full_path(self):
        lst = FileListWidget("Test")
        path = "/some/deep/folder/document.pdf"
        lst.addItem(path)

        item = lst.item(0)
        self.assertIn("document.pdf", item.text())
        self.assertNotIn("/some/deep", item.text())
        self.assertEqual(item.data(Qt.ItemDataRole.UserRole), path)
        self.assertEqual(item.toolTip(), path)
        self.assertEqual(lst.get_files(), [path])

    def test_additem_and_clear_emit_files_changed(self):
        lst = FileListWidget("Test")
        emissions = []
        lst.files_changed.connect(lambda: emissions.append(1))

        lst.addItem("/a/b.pdf")
        self.assertEqual(len(emissions), 1)
        lst.clear()
        self.assertEqual(len(emissions), 2)
        self.assertEqual(lst.get_files(), [])


class TestRunButtonGating(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_run_disabled_until_both_lists_populated(self):
        self.assertFalse(self.window.btn_run.isEnabled())

        self.window.reference_list.addItem("/tmp/ref.pdf")
        self.assertFalse(self.window.btn_run.isEnabled())

        self.window.target_list.addItem("/tmp/target.pdf")
        self.assertTrue(self.window.btn_run.isEnabled())

        self.window.reference_list.clear()
        self.assertFalse(self.window.btn_run.isEnabled())

    def test_run_disabled_while_comparison_running(self):
        self.window.reference_list.addItem("/tmp/ref.pdf")
        self.window.target_list.addItem("/tmp/target.pdf")
        self.assertTrue(self.window.btn_run.isEnabled())

        self.window._comparison_running = True
        self.window._update_run_enabled()
        self.assertFalse(self.window.btn_run.isEnabled())

        self.window._comparison_running = False
        self.window._update_run_enabled()
        self.assertTrue(self.window.btn_run.isEnabled())


class TestZoomIndicator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_zoom_status_label_tracks_zoom_level(self):
        window = MainWindow()
        try:
            self.assertEqual(window.lbl_zoom_status.text(), "Zoom 120%")
            window.change_zoom(0.1)
            self.assertEqual(window.lbl_zoom_status.text(), "Zoom 130%")
            window.reset_zoom()
            self.assertEqual(window.lbl_zoom_status.text(), "Zoom 120%")
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
