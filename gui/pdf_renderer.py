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
    LRU cache for rendered PDF page pixmaps with memory-aware eviction.

    Keys are tuples of (file_path, page_idx, zoom_level).
    Evicts least-recently-used entries once the estimated RAM footprint
    exceeds *max_bytes* (default 256 MB), rather than a fixed page count.
    """

    # Default per-renderer budget (bytes)
    DEFAULT_MAX_BYTES: int = 256 * 1024 * 1024  # 256 MB

    def __init__(self, max_bytes: int = DEFAULT_MAX_BYTES):
        self.max_bytes = max_bytes
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._used_bytes: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pixmap_bytes(pixmap: QPixmap) -> int:
        """Estimate RAM footprint of a QPixmap (4 bytes per pixel, BGRA layout)."""
        if pixmap.isNull():
            return 0
        return pixmap.width() * pixmap.height() * 4

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: tuple) -> Optional[QPixmap]:
        """Retrieve a cached pixmap, promoting it to MRU position."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: tuple, pixmap: QPixmap) -> None:
        """Store a pixmap, evicting LRU entries until under the byte budget."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return

        size = self._pixmap_bytes(pixmap)
        # Always keep at least one entry even if it exceeds the budget alone
        while self._used_bytes + size > self.max_bytes and self._cache:
            _, evicted = self._cache.popitem(last=False)
            self._used_bytes -= self._pixmap_bytes(evicted)
            del evicted

        self._cache[key] = pixmap
        self._used_bytes += size

    def clear(self) -> None:
        """Remove all entries and reset the byte counter."""
        self._cache.clear()
        self._used_bytes = 0

    def invalidate_file(self, file_path: str) -> None:
        """Remove all entries for a specific file."""
        keys_to_remove = [k for k in self._cache if k[0] == file_path]
        for key in keys_to_remove:
            self._used_bytes -= self._pixmap_bytes(self._cache[key])
            del self._cache[key]

    @property
    def used_bytes(self) -> int:
        """Current estimated RAM used by cached pixmaps."""
        return self._used_bytes

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

    def __init__(self, max_bytes: int = PixmapCache.DEFAULT_MAX_BYTES):
        super().__init__()
        self.pixmap_cache = PixmapCache(max_bytes=max_bytes)
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

    def get_page_dimensions(
        self, file_path: str, zoom: float
    ) -> list[tuple[float, float]]:
        """
        Open fitz once and return (width_px, height_px) for every page at the given zoom.

        Args:
            file_path: Path to the PDF file
            zoom: Zoom level (1.0 = 100%)

        Returns:
            List of (width_px, height_px) tuples for each page
        """
        zoom_key = round(zoom, 2)
        doc = fitz.open(file_path)
        dims = []
        try:
            for page in doc:
                rect = page.rect
                dims.append((rect.width * zoom_key, rect.height * zoom_key))
        finally:
            doc.close()
        return dims

    def batch_prerender(
        self,
        file_path: str,
        page_indices: list,
        zoom: float,
        doc=None,
    ) -> None:
        """
        Render all uncached pages from page_indices into the pixmap cache.

        Opens fitz once (or reuses an already-open doc) to avoid N fitz.open() calls.

        Args:
            file_path: Path to the PDF file
            page_indices: List of zero-indexed page numbers to prerender
            zoom: Zoom level
            doc: Optional already-open fitz.Document to reuse
        """
        zoom_key = round(zoom, 2)
        uncached = [
            idx
            for idx in page_indices
            if self.pixmap_cache.get((file_path, idx, zoom_key)) is None
        ]
        if not uncached:
            return

        should_close = doc is None
        if doc is None:
            doc = fitz.open(file_path)
        try:
            for page_idx in uncached:
                page = doc[page_idx]
                mat = fitz.Matrix(zoom_key, zoom_key)
                pix = page.get_pixmap(matrix=mat)
                qimg = QImage(
                    pix.samples,
                    pix.width,
                    pix.height,
                    pix.stride,
                    QImage.Format.Format_RGB888,
                ).copy()
                pixmap = QPixmap.fromImage(qimg)
                self.pixmap_cache.put((file_path, page_idx, zoom_key), pixmap)
        finally:
            if should_close:
                doc.close()

    def store_pixmap(
        self, file_path: str, page_idx: int, zoom: float, pixmap: QPixmap
    ) -> None:
        """Insert a pre-rendered pixmap directly into the cache."""
        zoom_key = round(zoom, 2)
        self.pixmap_cache.put((file_path, page_idx, zoom_key), pixmap)

    def get_cache_stats(self) -> dict:
        """Return cache statistics for display."""
        return {
            "cached_pages": len(self.pixmap_cache),
            "used_bytes": self.pixmap_cache.used_bytes,
        }
