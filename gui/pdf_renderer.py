"""
PDF Rendering Engine with LRU Caching.

This module extracts rendering responsibilities from MainWindow to provide:
- LRU-cached pixmap generation for efficient zoom/scroll
- Centralized PDF rendering logic
- Clean separation of concerns
"""

import fitz
from collections import OrderedDict
from typing import Optional
from PyQt6.QtGui import QImage, QPixmap, QColor
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtCore import QObject, pyqtSignal

from gui.widgets import PDFPageLabel


class PixmapCache:
    """
    LRU cache for rendered PDF page pixmaps.

    Keys are tuples of (file_path, page_idx, zoom_level).
    Automatically evicts least-recently-used entries when capacity is exceeded.
    """

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()

    def get(self, key: tuple) -> Optional[QPixmap]:
        """Retrieve a cached pixmap, moving it to the end (most recently used)."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: tuple, pixmap: QPixmap) -> None:
        """Store a pixmap in the cache, evicting LRU entries if necessary."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return

        # Evict if at capacity
        while len(self._cache) >= self.max_size:
            evicted_key, evicted_pix = self._cache.popitem(last=False)
            del evicted_pix

        self._cache[key] = pixmap

    def clear(self) -> None:
        """Clear all cached pixmaps."""
        self._cache.clear()

    def invalidate_file(self, file_path: str) -> None:
        """Remove all cached entries for a specific file."""
        keys_to_remove = [k for k in self._cache if k[0] == file_path]
        for key in keys_to_remove:
            del self._cache[key]

    def __len__(self) -> int:
        return len(self._cache)


class PDFRenderer(QObject):
    """
    High-performance PDF rendering engine with caching.

    Features:
    - LRU pixmap cache to avoid redundant rendering
    - Efficient highlight overlay rendering
    - Clean widget lifecycle management
    """

    # Signals for async operations
    page_rendered = pyqtSignal(int, object)  # page_idx, PDFPageLabel
    render_complete = pyqtSignal()

    def __init__(self, cache_size: int = 100):
        super().__init__()
        self.pixmap_cache = PixmapCache(max_size=cache_size)
        self._current_file: Optional[str] = None
        self._current_zoom: float = 1.0

    def get_cached_pixmap(self, file_path: str, page_idx: int, zoom: float) -> QPixmap:
        """
        Get a pixmap for a PDF page, using cache if available.

        Args:
            file_path: Path to the PDF file
            page_idx: Zero-indexed page number
            zoom: Zoom level (1.0 = 100%)

        Returns:
            A QPixmap of the rendered page
        """
        # Round zoom for cache key consistency
        zoom_key = round(zoom, 2)
        cache_key = (file_path, page_idx, zoom_key)

        # Try cache first
        pixmap = self.pixmap_cache.get(cache_key)

        if pixmap is None:
            # Render fresh
            pixmap = self._render_pixmap(file_path, page_idx, zoom)
            self.pixmap_cache.put(cache_key, pixmap)

        return pixmap

    def _render_pixmap(self, file_path: str, page_idx: int, zoom: float) -> QPixmap:
        """Generate a QPixmap from a PDF page."""
        doc = fitz.open(file_path)
        try:
            page = doc[page_idx]
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            qimg = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            ).copy()  # Copy to own the data

            return QPixmap.fromImage(qimg)
        finally:
            doc.close()

    def render_document(
        self,
        file_path: str,
        zoom: float,
        results: dict = None,
        color_map: dict = None,
        container_layout: QVBoxLayout = None,
        hover_enabled: bool = True,
        match_clicked_callback=None,
        match_ignored_callback=None,
    ) -> list[PDFPageLabel]:
        """
        Render all pages of a PDF document.

        Args:
            file_path: Path to the PDF file
            zoom: Zoom level
            results: Dictionary mapping page_idx to list of matches
            color_map: Source-to-color mapping
            container_layout: Optional layout to add widgets to
            hover_enabled: Whether hover previews are enabled
            match_clicked_callback: Callback for match click events
            match_ignored_callback: Callback for match ignore events

        Returns:
            List of rendered PDFPageLabel widgets
        """
        results = results or {}
        color_map = color_map or {}

        # Clear container layout if provided
        if container_layout:
            while container_layout.count():
                item = container_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        doc = fitz.open(file_path)
        page_count = len(doc)
        doc.close()

        widgets = []

        for page_idx in range(page_count):
            # Get cached or fresh pixmap
            pixmap = self.get_cached_pixmap(file_path, page_idx, zoom)

            # Build highlights for this page
            highlights = []
            if page_idx in results:
                for m in results[page_idx]:
                    highlights.append(
                        {
                            "rect": fitz.Rect(
                                m["rect"].x0 * zoom,
                                m["rect"].y0 * zoom,
                                m["rect"].x1 * zoom,
                                m["rect"].y1 * zoom,
                            ),
                            "source": m["source"],
                            "source_data": m["source_data"],
                            "match_id": m.get("match_id"),
                        }
                    )

            # Create fresh widget with cached pixmap
            widget = PDFPageLabel(pixmap, highlights, color_map)
            widget.page_index = page_idx
            widget.show_hover_previews = hover_enabled

            if match_clicked_callback:
                widget.matchesClicked.connect(match_clicked_callback)
            if match_ignored_callback:
                widget.matchIgnored.connect(match_ignored_callback)

            widgets.append(widget)

            if container_layout:
                container_layout.addWidget(widget)
                container_layout.addSpacing(10)

        self._current_file = file_path
        self._current_zoom = zoom

        return widgets

    def render_source_document(
        self,
        file_path: str,
        zoom: float,
        source_data: list,
        highlight_color: QColor,
        container_layout: QVBoxLayout = None,
    ) -> tuple[list[PDFPageLabel], str, int]:
        """
        Render a source document with match highlights.

        Returns:
            Tuple of (widgets, full_text, target_page_idx)
        """
        # Clear container layout if provided
        if container_layout:
            while container_layout.count():
                item = container_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        doc = fitz.open(file_path)
        widgets = []
        full_text = ""
        target_page = source_data[0][0] if source_data else 0

        for page_idx, page in enumerate(doc):
            # Get cached or fresh pixmap
            pixmap = self.get_cached_pixmap(file_path, page_idx, zoom)

            # Build highlights from source_data
            page_rects = [x[1] for x in source_data if x[0] == page_idx]
            page_rects.sort(key=lambda r: (r.y0, r.x0))

            # Merge adjacent rects
            merged_rects = []
            if page_rects:
                curr = page_rects[0]
                for nxt in page_rects[1:]:
                    if (
                        max(0, min(curr.y1, nxt.y1) - max(curr.y0, nxt.y0))
                        > (curr.y1 - curr.y0) * 0.5
                        and nxt.x0 - curr.x1 < 30
                    ):
                        curr.x1 = max(curr.x1, nxt.x1)
                    else:
                        merged_rects.append(curr)
                        curr = nxt
                merged_rects.append(curr)

            highlights = [
                {
                    "rect": fitz.Rect(
                        r.x0 * zoom, r.y0 * zoom, r.x1 * zoom, r.y1 * zoom
                    ),
                    "source": "SELECTION",
                }
                for r in merged_rects
            ]

            color_map = {"SELECTION": highlight_color}
            widget = PDFPageLabel(pixmap, highlights, color_map)
            widget.page_index = page_idx
            widgets.append(widget)

            if container_layout:
                container_layout.addWidget(widget)
                container_layout.addSpacing(10)

            full_text += f"--- Page {page_idx + 1} ---\n{page.get_text('text')}\n\n"

        doc.close()
        return widgets, full_text, target_page

    def invalidate_cache(self, file_path: Optional[str] = None) -> None:
        """Clear cache entries, optionally for a specific file."""
        if file_path:
            self.pixmap_cache.invalidate_file(file_path)
        else:
            self.pixmap_cache.clear()

    def cleanup(self) -> None:
        """Release all resources."""
        self.pixmap_cache.clear()

    def get_cache_stats(self) -> dict:
        """Return cache statistics for debugging."""
        return {
            "cached_pages": len(self.pixmap_cache),
        }
