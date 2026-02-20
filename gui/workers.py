"""
Background Workers for PDFCompare.

This module provides QThread-based workers for:
- IndexWorker: Parallel reference document indexing
- CompareWorker: Document comparison with progress reporting
- PreviewWorker: Background image preview generation
"""

import fitz
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool
from PyQt6.QtGui import QImage, QPixmap, QColor, QPainter
from PyQt6.QtCore import QRectF, Qt


class CompareWorker(QObject):
    """
    Worker for running document comparison in background thread.

    Emits progress updates during comparison phases.
    """

    finished = pyqtSignal(dict, int, dict)  # results, total_words, source_stats
    progress = pyqtSignal(int, str)  # percent, message
    error = pyqtSignal(str)

    def __init__(
        self, comparator, target_path, mode="fast", use_sw=True, sw_expansion=1
    ):
        super().__init__()
        self.comparator = comparator
        self.target_path = target_path
        self.mode = mode
        self.use_sw = use_sw
        self.sw_expansion = sw_expansion

    def run(self):
        def progress_callback(percent: int, message: str):
            self.progress.emit(percent, message)

        try:
            results, total_words, source_stats = self.comparator.compare_document(
                self.target_path,
                mode=self.mode,
                use_sw=self.use_sw,
                sw_expansion=self.sw_expansion,
                progress_callback=progress_callback,
            )
            self.finished.emit(results, total_words, source_stats)
        except Exception as e:
            self.error.emit(str(e))


class IndexWorker(QObject):
    """
    Worker for indexing reference documents in background thread.

    Emits progress updates as files are processed.
    """

    finished = pyqtSignal()
    progress = pyqtSignal(int, str)  # percent, message
    error = pyqtSignal(str)

    def __init__(self, comparator, file_paths):
        super().__init__()
        self.comparator = comparator
        self.file_paths = file_paths

    def run(self):
        def progress_callback(current: int, total: int):
            percent = int((current / total) * 100) if total > 0 else 0
            message = f"Indexing file {current}/{total}..."
            self.progress.emit(percent, message)

        try:
            self.comparator.add_references(self.file_paths, progress_callback)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class PreviewSignals(QObject):
    """Signals for PreviewWorker (QRunnable can't have signals directly)."""

    finished = pyqtSignal(list, list)  # pixmaps, match_ids


class PreviewWorker(QRunnable):
    """
    Worker for generating match preview images in background.

    Uses QThreadPool for efficient thread reuse.
    Generates cropped, highlighted images of source matches.
    """

    def __init__(self, matches: list, color_map: dict, match_ids: list):
        super().__init__()
        self.matches = matches
        self.color_map = color_map
        self.match_ids = match_ids
        self.signals = PreviewSignals()
        self._cancelled = False

        # Auto-delete when done
        self.setAutoDelete(True)

    def cancel(self):
        """Mark this worker as cancelled."""
        self._cancelled = True

    def run(self):
        """Generate preview images for all matches."""
        if self._cancelled:
            return

        pixmaps = []

        for match in self.matches:
            if self._cancelled:
                return

            source_path = match.get("source")
            data = match.get("source_data")
            if not source_path or not data:
                continue

            page_idx = data[0][0]
            rects = [fitz.Rect(item[1]) for item in data if item[0] == page_idx]
            if not rects:
                continue

            # Calculate bounding box
            bbox = rects[0]
            for r in rects[1:]:
                bbox |= r

            # Add margin
            margin = 30
            bbox.x0 = max(0, bbox.x0 - margin)
            bbox.y0 = max(0, bbox.y0 - margin)
            bbox.x1 += margin
            bbox.y1 += margin

            # Render page region
            doc = fitz.open(source_path)
            page = doc[page_idx]
            zoom = 1.5
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=bbox)

            qimg = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            ).copy()

            doc.close()

            # Draw highlights
            painter = QPainter(qimg)
            color = self.color_map.get(source_path, QColor(255, 0, 0, 60))
            if color.alpha() < 80:
                color.setAlpha(80)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)

            for r in rects:
                rx0 = (r.x0 - bbox.x0) * zoom
                ry0 = (r.y0 - bbox.y0) * zoom
                painter.drawRect(QRectF(rx0, ry0, r.width * zoom, r.height * zoom))

            painter.end()
            pixmaps.append(QPixmap.fromImage(qimg))

        if not self._cancelled:
            self.signals.finished.emit(pixmaps, self.match_ids)


# Global thread pool for preview generation
_preview_pool = None


def get_preview_pool() -> QThreadPool:
    """Get or create the preview thread pool."""
    global _preview_pool
    if _preview_pool is None:
        _preview_pool = QThreadPool()
        _preview_pool.setMaxThreadCount(2)  # Limit concurrent previews
    return _preview_pool


class PageRenderWorkerSignals(QObject):
    """Signals for PageRenderWorker."""

    # list of (page_idx: int, image: QImage), plus the zoom the render was for
    finished = pyqtSignal(list, float)


class PageRenderWorker(QRunnable):
    """
    Background worker that rasterises a set of PDF pages into QImage objects.

    Uses QImage (thread-safe) rather than QPixmap; the caller converts to
    QPixmap on the main thread via _on_bg_pages_rendered.
    """

    def __init__(self, file_path: str, page_indices: list, zoom: float):
        super().__init__()
        self.file_path = file_path
        self.page_indices = page_indices
        self.zoom = round(zoom, 2)
        self.signals = PageRenderWorkerSignals()
        self._cancelled = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        if self._cancelled:
            return

        results = []
        doc = fitz.open(self.file_path)
        try:
            mat = fitz.Matrix(self.zoom, self.zoom)
            for page_idx in self.page_indices:
                if self._cancelled:
                    return
                pix = doc[page_idx].get_pixmap(matrix=mat)
                qimg = QImage(
                    pix.samples,
                    pix.width,
                    pix.height,
                    pix.stride,
                    QImage.Format.Format_RGB888,
                ).copy()  # detach from fitz buffer
                results.append((page_idx, qimg))
        finally:
            doc.close()

        if not self._cancelled:
            self.signals.finished.emit(results, self.zoom)
