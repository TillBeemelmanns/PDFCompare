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
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import QObject


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

    def __init__(self, max_bytes: int = PixmapCache.DEFAULT_MAX_BYTES):
        super().__init__()
        self.pixmap_cache = PixmapCache(max_bytes=max_bytes)

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
