import os
import sys
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QImage, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.main_window import MainWindow
from gui.workers import PageRenderWorker


class TestTargetScrollRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.pdf_path = "tests/_gui_scroll.pdf"

        doc = fitz.open()
        for page_idx in range(24):
            page = doc.new_page(width=612, height=792)
            page.insert_text(
                (50, 50),
                f"Scroll regression page {page_idx + 1}. " + ("content " * 120),
            )
        doc.save(cls.pdf_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)

    def setUp(self):
        self.window = MainWindow()
        self.window.chk_minimap.setChecked(False)
        self.window.show()
        self._wait(100)

    def tearDown(self):
        self.window.clear_results()
        self.window._bg_render_pool.waitForDone(5000)
        self.window.close()
        self._wait(50)

    def _wait(self, ms: int) -> None:
        QTest.qWait(ms)

    def _wait_until(self, predicate, timeout_ms: int = 4000, step_ms: int = 20) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if predicate():
                return True
            self._wait(step_ms)
        return predicate()

    def _send_wheel(self, angle_delta_y: int = -960) -> None:
        viewport = self.window.target_scroll.viewport()
        center = viewport.rect().center()
        pos = QPointF(center)
        global_pos = QPointF(viewport.mapToGlobal(center))
        event = QWheelEvent(
            pos,
            global_pos,
            QPoint(0, 0),
            QPoint(0, angle_delta_y),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(viewport, event)
        self.window.repaint()
        self._wait(5)

    def _render_target(self) -> None:
        self.window.current_target_file = self.pdf_path
        doc = fitz.open(self.pdf_path)
        try:
            self.window.current_total_pages = len(doc)
            self.window.current_page_heights = [page.rect.height for page in doc]
        finally:
            doc.close()
        self.window.render_target(self.pdf_path, {})
        self.assertTrue(
            self._wait_until(
                lambda: self.window.target_scroll.verticalScrollBar().maximum() > 0
            )
        )

    def test_stale_target_render_callback_is_ignored(self):
        self._render_target()

        stale_epoch = self.window._target_render_epoch
        stale_file = self.window._target_virtual_file
        page_idx = 10
        cache_key = (stale_file, page_idx, round(self.window.zoom_level, 2))

        self.window.render_target(self.pdf_path, {}, restore_scroll=300)
        self._wait(50)

        image = QImage(32, 32, QImage.Format.Format_RGB888)
        image.fill(0)
        stale_worker = PageRenderWorker(stale_file, [page_idx], self.window.zoom_level)
        self.window._on_bg_pages_rendered(
            [(page_idx, image)],
            round(self.window.zoom_level, 2),
            stale_file,
            stale_epoch,
            stale_worker,
        )

        self.assertIsNone(self.window.target_renderer.pixmap_cache.get(cache_key))

    def test_target_wheel_scroll_does_not_snap_back_during_async_render(self):
        original_run = PageRenderWorker.run

        def delayed_run(worker):
            time.sleep(0.05)
            return original_run(worker)

        with mock.patch.object(PageRenderWorker, "run", delayed_run):
            self._render_target()

            bar = self.window.target_scroll.verticalScrollBar()
            self.assertEqual(bar.value(), 0)

            target_value = max(int(bar.maximum() * 0.6), 1)
            peak_value = bar.value()

            for _ in range(20):
                for _ in range(3):
                    self._send_wheel(-960)
                    peak_value = max(peak_value, bar.value())
                    if peak_value >= target_value:
                        break
                self._wait(70)
                peak_value = max(peak_value, bar.value())
                if peak_value >= target_value:
                    break

            self.assertGreaterEqual(
                peak_value,
                target_value,
                f"scrollbar only reached {peak_value} / {bar.maximum()}",
            )

            self.assertTrue(
                self._wait_until(
                    lambda: self.window._pending_bg_render_worker is None,
                    timeout_ms=5000,
                )
            )
            self._wait(250)

            final_value = bar.value()
            min_expected = max(
                int(bar.maximum() * 0.35),
                peak_value - self.window.target_scroll.viewport().height(),
            )
            self.assertGreaterEqual(
                final_value,
                min_expected,
                f"scrollbar snapped back from {peak_value} to {final_value}",
            )


if __name__ == "__main__":
    unittest.main()
