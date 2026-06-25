"""
Virtualized PDF page view engine.

`VirtualPdfView` owns the per-viewer virtual-scroll state and machinery that
was previously duplicated across the "target" and "source" code paths in
``MainWindow`` (and accessed through a string-keyed ``_VIEW_ATTRS`` table).

Each viewer (target document, reference document) is a single instance. The
view manages page geometry, lazy materialization/dematerialization of page
pixmaps near the viewport, scroll anchoring across rebuilds, and dispatch of
uncached pages to the shared background render pool.

Widget *creation* (and the highlight construction that depends on comparison
results) stays in ``MainWindow``; the view only owns the recycled
``PDFPageLabel`` slots and their materialization lifecycle.

Shared resources (zoom level, the recycled-widget pool, the background render
``QThreadPool``) live on the owning window and are reached via ``self.window``.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from gui.workers import PageRenderWorker

if TYPE_CHECKING:
    from gui.main_window import MainWindow
    from gui.pdf_renderer import PDFRenderer
    from PyQt6.QtWidgets import QScrollArea, QWidget


class VirtualPdfView:
    """Virtual-scroll page engine for a single PDF viewer."""

    PAGE_GAP = 10

    def __init__(
        self,
        window: "MainWindow",
        renderer: "PDFRenderer",
        scroll: "QScrollArea",
        container: "QWidget",
    ):
        self.window = window
        self.renderer = renderer
        self.scroll = scroll
        self.container = container

        # Virtual scroll state
        self.slots: list = []
        self.slot_data: list = []
        self.dims: list = []
        self.offsets: list = []
        self.file: str | None = None
        self.render_epoch: int = 0
        self.pending_worker: PageRenderWorker | None = None
        # Zoom level the current page widgets were built for (target fast-path).
        self.rendered_zoom: float = 0.0

    # ------------------------------------------------------------------
    # Render-epoch bookkeeping
    # ------------------------------------------------------------------

    def bump_render_epoch(self) -> int:
        """Advance and return the render epoch for this view."""
        self.render_epoch += 1
        return self.render_epoch

    def is_current_render(self, file_path: str, render_epoch: int) -> bool:
        """Return True only for callbacks belonging to the active render."""
        return render_epoch == self.render_epoch and file_path == self.file

    # ------------------------------------------------------------------
    # Page geometry
    # ------------------------------------------------------------------

    def _build_y_offsets(self, page_dims: list[tuple[int, int]]) -> list[int]:
        """Compute the cumulative y offset for each page in the canvas."""
        y_offsets: list[int] = []
        y = 0
        for _w, h in page_dims:
            y_offsets.append(y)
            y += int(h) + self.PAGE_GAP
        return y_offsets

    def set_page_geometry(self, page_dims: list[tuple[int, int]]) -> None:
        """Store page dimensions, derived offsets, and resize the canvas widget."""
        self.dims = page_dims
        self.offsets = self._build_y_offsets(page_dims)
        self.resize_container()

    def resize_container(self) -> None:
        """Resize the virtualized canvas to cover all pages."""
        total_h = (
            int(self.offsets[-1] + self.dims[-1][1] + self.PAGE_GAP) if self.dims else 0
        )
        max_w = max((int(w) for w, _h in self.dims), default=0)
        self.container.setMinimumSize(max_w, total_h)
        self.container.resize(max_w, total_h)

    # ------------------------------------------------------------------
    # Scroll anchoring
    # ------------------------------------------------------------------

    def capture_scroll_anchor(
        self, scroll_value: int | None = None
    ) -> tuple[int, int] | None:
        """Capture the top-of-viewport anchor as (page_idx, offset_from_page_top)."""
        if not self.offsets or not self.dims:
            return None

        if scroll_value is None:
            scroll_value = self.scroll.verticalScrollBar().value()

        page_idx = bisect_right(self.offsets, scroll_value) - 1
        page_idx = max(0, min(page_idx, len(self.offsets) - 1))
        page_top = int(self.offsets[page_idx])
        max_offset = int(self.dims[page_idx][1]) + self.PAGE_GAP
        offset = max(0, min(int(scroll_value - page_top), max_offset))
        return page_idx, offset

    def scroll_value_from_anchor(self, anchor: tuple[int, int] | None) -> int:
        """Convert a stored page anchor back into a scrollbar value."""
        if anchor is None or not self.offsets or not self.dims:
            return 0

        page_idx, offset = anchor
        page_idx = max(0, min(int(page_idx), len(self.offsets) - 1))
        max_offset = int(self.dims[page_idx][1]) + self.PAGE_GAP
        offset = max(0, min(int(offset), max_offset))
        return int(self.offsets[page_idx] + offset)

    # ------------------------------------------------------------------
    # Widget slot lifecycle
    # ------------------------------------------------------------------

    def cancel_pending_worker(self) -> None:
        """Cancel and clear any in-flight background page renderer."""
        if self.pending_worker is not None:
            self.pending_worker.cancel()
            self.pending_worker = None

    def recycle_page_slots(self) -> None:
        """Pool or delete all page widgets currently owned by this view."""
        for lbl in self.slots:
            if len(self.window.widget_pool) < self.window._MAX_POOL_SIZE:
                lbl.setParent(None)
                lbl.hide()
                self.window.widget_pool.append(lbl)
            else:
                lbl.deleteLater()
        self.slots = []
        self.slot_data = []

    # ------------------------------------------------------------------
    # Viewport materialization
    # ------------------------------------------------------------------

    def get_render_zone(self) -> tuple[int, int]:
        """Return the vertical buffer zone to materialize for the viewport."""
        viewport_height = self.scroll.viewport().height()
        scroll_value = self.scroll.verticalScrollBar().value()
        render_top = max(0, scroll_value - viewport_height)
        render_bottom = scroll_value + 2 * viewport_height
        return render_top, render_bottom

    def partition_pages_by_zone(
        self, render_top: int, render_bottom: int
    ) -> tuple[list[int], list[int]]:
        """Split page indices into in-zone and out-of-zone groups."""
        pages_in_zone: list[int] = []
        pages_out_of_zone: list[int] = []

        for page_idx, (y_off, (_w, h)) in enumerate(zip(self.offsets, self.dims)):
            if y_off + h >= render_top and y_off <= render_bottom:
                pages_in_zone.append(page_idx)
            else:
                pages_out_of_zone.append(page_idx)

        return pages_in_zone, pages_out_of_zone

    def start_background_render(self, page_indices: list[int]) -> None:
        """Queue uncached pages for asynchronous rendering."""
        self.cancel_pending_worker()
        render_epoch = self.render_epoch
        file_path = self.file
        worker = PageRenderWorker(file_path, page_indices, self.window.zoom_level)
        worker.signals.finished.connect(
            lambda results, zoom, worker=worker, file_path=file_path, render_epoch=render_epoch: (
                self.handle_bg_pages_rendered(
                    results, zoom, file_path, render_epoch, worker
                )
            )
        )
        self.pending_worker = worker
        self.window._bg_render_pool.start(worker)

    def update_visible_pages(self) -> None:
        """Materialize nearby pages and dematerialize distant pages."""
        if not self.slots:
            return

        render_top, render_bottom = self.get_render_zone()
        pages_in_zone, pages_out_of_zone = self.partition_pages_by_zone(
            render_top, render_bottom
        )

        zoom_key = round(self.window.zoom_level, 2)
        cached_in_zone = [
            page_idx
            for page_idx in pages_in_zone
            if self.renderer.pixmap_cache.get((self.file, page_idx, zoom_key))
            is not None
        ]
        cached_set = set(cached_in_zone)
        uncached_in_zone = [
            page_idx for page_idx in pages_in_zone if page_idx not in cached_set
        ]

        for page_idx in cached_in_zone:
            self.materialize_page(page_idx)

        if uncached_in_zone:
            self.start_background_render(uncached_in_zone)

        for page_idx in pages_out_of_zone:
            self.dematerialize_page(page_idx)

    def materialize_page(self, page_idx: int) -> None:
        """Set the rendered pixmap on a page label and show it."""
        if self.slot_data[page_idx]["materialized"]:
            return

        lbl = self.slots[page_idx]
        pixmap = self.renderer.get_cached_pixmap(
            self.file, page_idx, self.window.zoom_level
        )
        lbl.original_pixmap = pixmap
        lbl.move(0, int(self.offsets[page_idx]))
        lbl.show()
        if lbl.highlights:
            lbl.draw_highlights()
        else:
            lbl.setPixmap(lbl.original_pixmap)
        self.slot_data[page_idx]["materialized"] = True

    def dematerialize_page(self, page_idx: int) -> None:
        """Hide a page and clear its pixmap to free RAM."""
        if not self.slot_data[page_idx]["materialized"]:
            return

        lbl = self.slots[page_idx]
        if lbl.hasFocus():
            lbl.clearFocus()
            self.scroll.setFocus(Qt.FocusReason.OtherFocusReason)
        lbl.hide()
        lbl.original_pixmap = QPixmap()
        lbl.setPixmap(QPixmap())
        lbl._hl_cache = None
        lbl._hl_cache_key = None
        self.slot_data[page_idx]["materialized"] = False

    def handle_bg_pages_rendered(
        self,
        results: list,
        zoom: float,
        file_path: str,
        render_epoch: int,
        worker: PageRenderWorker,
    ) -> None:
        """Convert rendered images to pixmaps, cache them, materialize in-zone pages."""
        if self.pending_worker is worker:
            self.pending_worker = None

        if (
            not self.slots
            or not self.is_current_render(file_path, render_epoch)
            or zoom != round(self.window.zoom_level, 2)
        ):
            return

        for page_idx, qimg in results:
            self.renderer.store_pixmap(
                self.file, page_idx, zoom, QPixmap.fromImage(qimg)
            )

        render_top, render_bottom = self.get_render_zone()
        for page_idx, _ in results:
            if page_idx >= len(self.slot_data):
                continue
            y_off = self.offsets[page_idx]
            _w, h = self.dims[page_idx]
            if y_off + h >= render_top and y_off <= render_bottom:
                self.materialize_page(page_idx)

    # ------------------------------------------------------------------
    # "Only if still current" callback guards (used by deferred QTimers)
    # ------------------------------------------------------------------

    def update_visible_pages_if_current(
        self, file_path: str, render_epoch: int
    ) -> None:
        """Run materialization only if the callback still belongs to this render."""
        if self.is_current_render(file_path, render_epoch):
            self.update_visible_pages()

    def restore_scroll_anchor_if_current(
        self,
        anchor: tuple[int, int] | None,
        file_path: str,
        render_epoch: int,
    ) -> None:
        """Restore this view to its saved anchor only if the callback is current."""
        if not self.is_current_render(file_path, render_epoch):
            return
        self.scroll.verticalScrollBar().setValue(self.scroll_value_from_anchor(anchor))
        self.update_visible_pages()

    def scroll_to_if_current(
        self, scroll_y: int, file_path: str, render_epoch: int
    ) -> None:
        """Set the scrollbar to scroll_y and materialize, only if current."""
        if not self.is_current_render(file_path, render_epoch):
            return
        self.scroll.verticalScrollBar().setValue(scroll_y)
        self.update_visible_pages()
