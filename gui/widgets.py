"""
Custom Qt Widgets for PDFCompare.

This module provides specialized widgets for the PDF comparison interface:
- PreviewPopup: Floating tooltip for match previews
- FileListWidget: Drag-and-drop file list with enhanced UX
- PDFPageLabel: PDF page display with highlight overlays
- MiniMapWidget: Document navigation heatmap
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QMouseEvent,
    QAction,
    QPixmap,
    QLinearGradient,
    QFont,
    QPen,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QRectF,
    QSize,
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
)
import os


class PreviewPopup(QWidget):
    """
    Floating tooltip widget for displaying source match previews.

    Shows image snapshots of matched text in reference documents
    with navigation for multiple matches.
    """

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)

        # Image container
        self.lbl_image = QLabel("Loading...")
        self.lbl_image.setStyleSheet(
            "border: 1px solid #555; background: #222; color: #eee;"
        )
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.lbl_image)

        # Counter label
        self.lbl_counter = QLabel("")
        self.lbl_counter.setStyleSheet(
            "color: #aaa; font-size: 10px; background: rgba(0,0,0,150);"
        )
        self.lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_counter.setFixedSize(60, 15)
        self.lbl_counter.move(5, 5)  # Will be parented to image label
        self.lbl_counter.setParent(self.lbl_image)

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.images = []
        self.current_idx = 0

    def set_images(self, pixmaps):
        self.images = pixmaps
        self.current_idx = 0
        self.update_display()

    def cycle(self, delta):
        if not self.images:
            return
        self.current_idx = (self.current_idx + delta) % len(self.images)
        self.update_display()

    def update_display(self):
        if not self.images:
            self.set_loading()
            return

        pix = self.images[self.current_idx]
        self.lbl_image.setText("")
        self.lbl_image.setPixmap(pix)
        self.lbl_image.setFixedSize(pix.size())

        if len(self.images) > 1:
            self.lbl_counter.setText(f"{self.current_idx + 1} / {len(self.images)}")
            self.lbl_counter.show()
        else:
            self.lbl_counter.hide()

        self.adjustSize()

    def set_loading(self):
        self.lbl_image.setPixmap(QPixmap())
        self.lbl_image.setText("Loading Preview...")
        self.lbl_image.setFixedSize(QSize(200, 50))
        self.lbl_counter.hide()
        self.adjustSize()


class FileListWidget(QListWidget):
    """
    Enhanced drag-and-drop file list widget.

    Features:
    - Animated drop zone with glowing border
    - File count preview during drag
    - Validation feedback for non-PDF files
    - Support for folder drops (recursive PDF discovery)

    When single_file=True the widget only accepts a single PDF file:
    folders are rejected, multiple-file drops are rejected, and a new
    drop replaces the existing entry.
    """

    files_changed = pyqtSignal()  # Emitted when file list changes

    def __init__(self, title, parent=None, single_file=False):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.title = title
        self.single_file = single_file
        self.setAlternatingRowColors(True)
        self._setup_styles()
        self._drag_count = 0

        # Animation for glow effect
        self._glow_effect = QGraphicsDropShadowEffect(self)
        self._glow_effect.setBlurRadius(0)
        self._glow_effect.setColor(QColor(76, 175, 80, 180))  # Green glow
        self._glow_effect.setOffset(0, 0)
        self.setGraphicsEffect(self._glow_effect)

        # Fade animation
        self._glow_animation = QPropertyAnimation(self._glow_effect, b"blurRadius")
        self._glow_animation.setDuration(200)
        self._glow_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _setup_styles(self):
        """Apply modern styling to the widget."""
        self.setStyleSheet("""
            QListWidget {
                border: 2px dashed #4a4a5a;
                border-radius: 8px;
                background-color: #1e1e2e;
                color: #cdd6f4;
                padding: 8px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 8px 6px;
                border-radius: 4px;
                margin: 2px 0;
            }
            QListWidget::item:hover {
                background-color: #313244;
            }
            QListWidget::item:selected {
                background-color: #45475a;
                color: #f5f5f5;
            }
        """)

    def _start_drag_animation(self):
        """Start the glow animation on drag enter."""
        self._glow_animation.setStartValue(0)
        self._glow_animation.setEndValue(20)
        self._glow_animation.start()

        self.setStyleSheet("""
            QListWidget {
                border: 2px solid #4CAF50;
                border-radius: 8px;
                background-color: rgba(76, 175, 80, 0.1);
                color: #cdd6f4;
                padding: 8px;
            }
            QListWidget::item {
                padding: 8px 6px;
                border-radius: 4px;
            }
        """)

    def _end_drag_animation(self):
        """End the glow animation on drag leave."""
        self._glow_animation.setStartValue(20)
        self._glow_animation.setEndValue(0)
        self._glow_animation.start()
        self._setup_styles()

    def _show_invalid_feedback(self):
        """Show red feedback for invalid files."""
        self._glow_effect.setColor(QColor(239, 68, 68, 180))  # Red
        self._glow_animation.setStartValue(0)
        self._glow_animation.setEndValue(15)
        self._glow_animation.start()

        self.setStyleSheet("""
            QListWidget {
                border: 2px solid #ef4444;
                border-radius: 8px;
                background-color: rgba(239, 68, 68, 0.1);
                color: #cdd6f4;
                padding: 8px;
            }
        """)

        # Reset after delay
        QTimer.singleShot(500, self._end_drag_animation)
        QTimer.singleShot(
            500, lambda: self._glow_effect.setColor(QColor(76, 175, 80, 180))
        )

    def dragEnterEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        urls = event.mimeData().urls()

        if self.single_file:
            # Accept only a single, plain PDF file — no folders, no multi-drop.
            paths = [url.toLocalFile() for url in urls]
            if (
                len(paths) == 1
                and paths[0].lower().endswith(".pdf")
                and os.path.isfile(paths[0])
            ):
                event.acceptProposedAction()
                self._drag_count = 1
                self._start_drag_animation()
            else:
                self._show_invalid_feedback()
                event.ignore()
        else:
            pdf_count = sum(
                1
                for url in urls
                if url.toLocalFile().lower().endswith(".pdf")
                or os.path.isdir(url.toLocalFile())
            )
            if pdf_count > 0:
                event.acceptProposedAction()
                self._drag_count = pdf_count
                self._start_drag_animation()
            else:
                self._show_invalid_feedback()
                event.ignore()

    def dragLeaveEvent(self, event):
        self._end_drag_animation()
        self._drag_count = 0
        super().dragLeaveEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def _find_pdfs_recursive(self, path: str) -> list:
        """Recursively find all PDF files in a directory."""
        pdfs = []
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.lower().endswith(".pdf"):
                        pdfs.append(os.path.join(root, file))
        elif path.lower().endswith(".pdf"):
            pdfs.append(path)
        return pdfs

    def dropEvent(self, event):
        self._end_drag_animation()
        self._drag_count = 0

        if not event.mimeData().hasUrls():
            event.ignore()
            return

        if self.single_file:
            urls = event.mimeData().urls()
            if len(urls) == 1:
                path = urls[0].toLocalFile()
                if path.lower().endswith(".pdf") and os.path.isfile(path):
                    self.clear()
                    self.addItem(path)
                    event.acceptProposedAction()
                    self.files_changed.emit()
                    return
            self._show_invalid_feedback()
            event.ignore()
        else:
            added = 0
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                pdfs = self._find_pdfs_recursive(file_path)
                for pdf_path in pdfs:
                    existing = [self.item(i).text() for i in range(self.count())]
                    if pdf_path not in existing:
                        self.addItem(pdf_path)
                        added += 1

            if added > 0:
                event.acceptProposedAction()
                self.files_changed.emit()
            else:
                self._show_invalid_feedback()
                event.ignore()

    def get_files(self):
        return [self.item(i).text() for i in range(self.count())]

    def paintEvent(self, event):
        """Override to show placeholder when empty."""
        super().paintEvent(event)

        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Draw placeholder text
            font = QFont()
            font.setPointSize(11)
            painter.setFont(font)
            painter.setPen(QColor(100, 100, 120))

            rect = self.viewport().rect()
            if self.single_file:
                text = f"Drop {self.title} PDF here"
            else:
                text = f"Drop {self.title} PDF(s) here\nor drag folders"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

            painter.end()


class SourcePanelWidget(QWidget):
    selection_changed = pyqtSignal()
    file_browse_requested = pyqtSignal(str)  # emitted on filename-label click

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._total_rows = 0
        self._active_fp: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._summary_label = QLabel("No sources loaded")
        self._summary_label.setStyleSheet("font-size: 11px; color: #a6adc8;")
        layout.addWidget(self._summary_label)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by filename…")
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Min overlap:"))
        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.0, 100.0)
        self._threshold.setSingleStep(1.0)
        self._threshold.setSuffix(" %")
        self._threshold.setValue(0.0)
        self._threshold.valueChanged.connect(self._apply_filter)
        threshold_row.addWidget(self._threshold)
        layout.addLayout(threshold_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, 1)

    def populate(self, source_stats: dict, total_words: int) -> None:
        """Build rows sorted by match count descending."""
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()

        sorted_sources = sorted(
            source_stats.items(), key=lambda kv: kv[1], reverse=True
        )
        self._total_rows = len(sorted_sources)

        for fp, mc in sorted_sources:
            pct = (mc / total_words * 100) if total_words > 0 else 0.0
            row = self._make_row(fp, pct, mc)
            self._rows.append(
                {"fp": fp, "pct": pct, "chk": row["chk"], "row_widget": row["widget"]}
            )
            self._list_layout.insertWidget(self._list_layout.count() - 1, row["widget"])

        self._apply_filter()

    def _make_row(self, fp: str, pct: float, mc: int) -> dict:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(4, 2, 4, 2)
        vbox.setSpacing(1)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)

        # Indicator-only checkbox (no text) — toggles visibility of this source
        chk = QCheckBox()
        chk.setChecked(True)
        chk.setToolTip("Show/hide this source in the target view")
        chk.setFixedWidth(18)
        chk.stateChanged.connect(self.selection_changed)
        top.addWidget(chk)

        # Clickable filename label — single click solos this file and opens it
        name_lbl = QLabel(os.path.basename(fp))
        name_lbl.setStyleSheet("font-size: 11px;")
        name_lbl.setToolTip(fp)
        name_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        name_lbl.mousePressEvent = lambda event, _fp=fp: (
            self._on_row_click(_fp)
            if event.button() == Qt.MouseButton.LeftButton
            else None
        )
        top.addWidget(name_lbl, 1)

        stat = QLabel(f"{pct:.1f}% ({mc})")
        stat.setStyleSheet("font-size: 10px; color: #a6adc8;")
        top.addWidget(stat)
        vbox.addLayout(top)

        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(int(pct * 10))
        bar.setTextVisible(False)
        bar.setFixedHeight(4)
        bar.setStyleSheet(
            "QProgressBar { background: #313244; border-radius: 2px; }"
            "QProgressBar::chunk { background: rgba(250,170,30,180); border-radius: 2px; }"
        )
        vbox.addWidget(bar)

        # Use object-name selector so hover/active styles don't bleed into child widgets
        widget.setObjectName("source_row")
        widget.setStyleSheet(
            "#source_row { border-radius: 4px; }"
            "#source_row:hover { background: #313244; }"
        )
        return {"widget": widget, "chk": chk}

    def _on_row_click(self, fp: str) -> None:
        """Solo-select fp: check it, uncheck all others, then open in viewer."""
        for row in self._rows:
            row["chk"].blockSignals(True)
            row["chk"].setChecked(row["fp"] == fp)
            row["chk"].blockSignals(False)
        # Emit selection change once (re-filters the target view)
        self._apply_filter()
        # Open the file in the reference viewer
        self.file_browse_requested.emit(fp)

    def set_active_file(self, fp: str | None) -> None:
        """Highlight the row for the file currently shown in the reference viewer."""
        self._active_fp = fp
        for row in self._rows:
            if fp is not None and row["fp"] == fp:
                row["row_widget"].setStyleSheet(
                    "#source_row { border-radius: 4px; background: #2d2717;"
                    " border-left: 3px solid rgba(250,170,30,220); }"
                    "#source_row:hover { background: #342f1a; }"
                )
            else:
                row["row_widget"].setStyleSheet(
                    "#source_row { border-radius: 4px; }"
                    "#source_row:hover { background: #313244; }"
                )

    def _apply_filter(self) -> None:
        search = self._search.text().lower()
        min_pct = self._threshold.value()
        visible = 0
        for row in self._rows:
            show = (
                not search or search in os.path.basename(row["fp"]).lower()
            ) and row["pct"] >= min_pct
            row["row_widget"].setVisible(show)
            if show:
                visible += 1
        self._summary_label.setText(f"{visible} of {self._total_rows} sources active")
        self.selection_changed.emit()

    def get_active_files(self) -> set:
        """Return file paths that are checked AND currently visible (pass filter+threshold)."""
        return {
            row["fp"]
            for row in self._rows
            if row["chk"].isChecked() and row["row_widget"].isVisible()
        }

    def clear(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()
        self._total_rows = 0
        self._summary_label.setText("No sources loaded")


class PDFPageLabel(QLabel):
    """
    Widget for displaying PDF pages with interactive highlight overlays.

    Features:
    - Color-coded match highlighting
    - Hover tooltips with source previews (background loaded)
    - Click-to-trace match navigation
    - Context menu for match management
    """

    matchesClicked = pyqtSignal(list)
    matchIgnored = pyqtSignal(object)
    matchPhraseIgnored = pyqtSignal(
        object
    )  # emits match dict; main window writes phrase to disk
    show_hover_previews = True
    hl_intensity: float = 1.0  # Global multiplier for highlight alpha (0.25 – 2.0)
    min_confidence: float = 0.0  # Global minimum confidence threshold (0.0 – 1.0)

    _popup = None
    _pending_preview_worker = None  # Track current preview worker for cancellation

    def __init__(self, pixmap, highlights, color_map):
        super().__init__()
        self.original_pixmap = pixmap
        self.highlights = highlights
        self.color_map = color_map
        self.page_index = 0
        # Highlight-render cache: avoids redrawing when inputs haven't changed
        self._hl_cache: QPixmap | None = None
        self._hl_cache_key: tuple | None = None
        self.setPixmap(self.original_pixmap)
        self.draw_highlights()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.current_match_ids = []
        self._preview_request_ids = []  # Track which match_ids we requested previews for

        if PDFPageLabel._popup is None:
            PDFPageLabel._popup = PreviewPopup()

    def draw_highlights(self):
        if not self.highlights or self.original_pixmap.isNull():
            self.setPixmap(self.original_pixmap)
            self._hl_cache = None
            self._hl_cache_key = None
            return

        # Return cached result when highlights, pixmap, intensity, or threshold
        # have not changed since the last paint.
        cache_key = (
            id(self.highlights),
            id(self.original_pixmap),
            PDFPageLabel.hl_intensity,
            PDFPageLabel.min_confidence,
        )
        if cache_key == self._hl_cache_key and self._hl_cache is not None:
            self.setPixmap(self._hl_cache)
            return

        canvas = self.original_pixmap.copy()
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for h in self.highlights:
            if h.ignored:
                continue
            source = h.source
            rect = h.rect
            confidence = h.confidence

            if source in self.color_map:
                # Source-view sentinels ("CURRENT_MATCH", "OTHER_MATCH") keep explicit color
                base = self.color_map[source]
                color = QColor(base.red(), base.green(), base.blue(), base.alpha())
            else:
                # Skip matches below the global confidence threshold
                if confidence < PDFPageLabel.min_confidence:
                    continue

                # Two-tier coloring:
                #   Red/coral (critical) — confidence ≥ 0.80
                #   Amber (informational) — confidence < 0.80
                if confidence >= 0.80:
                    base_alpha = 50 + confidence * 80  # 114 … 130
                    alpha = int(min(255, base_alpha * PDFPageLabel.hl_intensity))
                    color = QColor(243, 139, 168, alpha)  # Catppuccin Red
                else:
                    base_alpha = 30 + confidence * 60
                    alpha = int(min(255, base_alpha * PDFPageLabel.hl_intensity))
                    color = QColor(250, 170, 30, alpha)  # Amber

            painter.setBrush(color)
            qrect = QRectF(rect.x0, rect.y0, rect.width, rect.height)

            # Red-tier matches always get a visible border
            if confidence >= 0.8 and source not in self.color_map:
                border_color = QColor(243, 139, 168, 180)
                pen = QPen(border_color)
                pen.setWidth(2)
                painter.setPen(pen)
            else:
                painter.setPen(Qt.PenStyle.NoPen)

            painter.drawRect(qrect)
        painter.end()

        self._hl_cache = canvas
        self._hl_cache_key = cache_key
        self.setPixmap(canvas)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.highlights:
            super().mouseMoveEvent(event)
            return

        pos = event.pos()
        x, y = pos.x(), pos.y()

        # Find ALL matches here
        matches_here = []
        for h in self.highlights:
            if h.ignored:
                continue
            r = h.rect
            if (r.x0 <= x <= r.x1) and (r.y0 <= y <= r.y1):
                matches_here.append(h)

        if matches_here:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            mids = [m.match_id for m in matches_here]

            if self.show_hover_previews:
                if mids != self.current_match_ids:
                    self.current_match_ids = mids
                    self.load_image_previews(matches_here)

                global_pos = self.mapToGlobal(event.position().toPoint())
                pop_pos = global_pos + QPoint(20, 20)
                screen = (
                    QApplication.screenAt(global_pos) or QApplication.primaryScreen()
                )
                if screen:
                    sg = screen.availableGeometry()
                    pw = self._popup.width() or 300
                    ph = self._popup.height() or 200
                    pop_pos.setX(min(pop_pos.x(), sg.right() - pw))
                    pop_pos.setY(min(pop_pos.y(), sg.bottom() - ph))
                    pop_pos.setX(max(pop_pos.x(), sg.left()))
                    pop_pos.setY(max(pop_pos.y(), sg.top()))
                self._popup.move(pop_pos)
                if not self._popup.isVisible():
                    self._popup.show()
                self._popup.raise_()
            else:
                if self._popup:
                    self._popup.hide()
                self.current_match_ids = []
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if self.hasFocus():
                self.clearFocus()
            if self._popup and self._popup.isVisible():
                self._popup.hide()
            self.current_match_ids = []
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if self._popup and self._popup.isVisible() and len(self.current_match_ids) > 1:
            if event.key() == Qt.Key.Key_Space:
                self._popup.cycle(1)
                return
        super().keyPressEvent(event)

    def leaveEvent(self, event):
        # Cancel any pending preview generation
        if PDFPageLabel._pending_preview_worker is not None:
            PDFPageLabel._pending_preview_worker.cancel()
            PDFPageLabel._pending_preview_worker = None

        if self._popup:
            self._popup.hide()
        self.current_match_ids = []
        self._preview_request_ids = []
        if self.hasFocus():
            self.clearFocus()
        super().leaveEvent(event)

    def load_image_previews(self, matches):
        """
        Load preview images asynchronously in background thread.

        Cancels any pending preview requests before starting new ones.
        """
        from gui.workers import PreviewWorker, get_preview_pool

        # Cancel any pending preview worker
        if PDFPageLabel._pending_preview_worker is not None:
            PDFPageLabel._pending_preview_worker.cancel()
            PDFPageLabel._pending_preview_worker = None

        # Show loading state immediately
        self._popup.set_loading()

        # Track which match_ids we're requesting
        match_ids = [m.match_id for m in matches]
        self._preview_request_ids = match_ids

        # Create worker
        worker = PreviewWorker(matches, self.color_map, match_ids)
        worker.signals.finished.connect(self._on_preview_loaded)

        # Track current worker
        PDFPageLabel._pending_preview_worker = worker

        # Submit to thread pool
        get_preview_pool().start(worker)

    def _on_preview_loaded(self, pixmaps: list, match_ids: list):
        """Handle completed preview generation."""
        # Check if this is still the current request (hasn't been superseded)
        if match_ids == self._preview_request_ids:
            self._popup.set_images(pixmaps)
            PDFPageLabel._pending_preview_worker = None

    def mousePressEvent(self, event: QMouseEvent):
        # Handle secondary mouse buttons for cycling
        if self._popup and self._popup.isVisible() and len(self.current_match_ids) > 1:
            if event.button() == Qt.MouseButton.XButton1:  # Back
                self._popup.cycle(-1)
                return
            elif event.button() == Qt.MouseButton.XButton2:  # Forward
                self._popup.cycle(1)
                return

        if event.button() == Qt.MouseButton.LeftButton:
            if not self.highlights:
                return
            pos = event.pos()
            x, y = pos.x(), pos.y()
            clicked = []
            for h in self.highlights:
                if h.ignored:
                    continue
                r = h.rect
                if (r.x0 <= x <= r.x1) and (r.y0 <= y <= r.y1):
                    if h.source_data:
                        clicked.append(h)
            if clicked:
                self.matchesClicked.emit(clicked)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        pos = event.pos()
        x, y = pos.x(), pos.y()
        match_under_cursor = None
        for h in self.highlights:
            if h.ignored:
                continue
            r = h.rect
            if (r.x0 <= x <= r.x1) and (r.y0 <= y <= r.y1):
                match_under_cursor = h
                break
        if match_under_cursor:
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background-color: #1e1e2e;
                    border: 1px solid #45475a;
                    border-radius: 6px;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 8px 20px;
                    color: #cdd6f4;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #45475a;
                }
            """)
            ignore_action = QAction("Ignore this match", self)
            ignore_action.triggered.connect(
                lambda: self.ignore_match(match_under_cursor)
            )
            menu.addAction(ignore_action)

            ignore_phrase_action = QAction("Ignore phrase globally", self)
            ignore_phrase_action.setToolTip(
                "Permanently exclude this phrase from all future comparisons.\n"
                "Saved to ~/.pdfcompare/ignored_phrases.txt"
            )
            ignore_phrase_action.triggered.connect(
                lambda: self.matchPhraseIgnored.emit(match_under_cursor)
            )
            menu.addAction(ignore_phrase_action)

            menu.exec(event.globalPos())

    def ignore_match(self, match):
        match.ignored = True
        self._hl_cache_key = None  # List mutated in-place — force a full repaint
        self.draw_highlights()
        self.matchIgnored.emit(match)


class MiniMapWidget(QWidget):
    """
    Document navigation heatmap widget.

    Provides a bird's-eye view of matches across the entire document
    with click-to-navigate functionality.
    """

    clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(28)
        self.matches = {}
        self.total_pages = 1
        self.page_heights = []
        self.viewport_pos = 0.0
        self.viewport_height = 0.1
        self.min_confidence = 0.0  # Synced with PDFPageLabel.min_confidence
        self._lines_cache: QPixmap | None = None  # Pre-rendered match markers

    def set_data(self, matches, total_pages, page_heights=None):
        self.matches = matches
        self.total_pages = max(1, total_pages)
        self.page_heights = page_heights or [800.0] * self.total_pages
        self._lines_cache = None  # Invalidate on data change
        self.update()

    def set_viewport(self, pos, height):
        self.viewport_pos = pos
        self.viewport_height = height
        self.update()

    def resizeEvent(self, event):
        self._lines_cache = None  # Invalidate on resize
        super().resizeEvent(event)

    def _build_lines_cache(self) -> None:
        """Pre-render all match markers into a QPixmap so paintEvent is cheap."""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        self._lines_cache = QPixmap(w, h)
        self._lines_cache.fill(Qt.GlobalColor.transparent)

        if not self.matches or not self.page_heights:
            return

        total_doc_height = sum(self.page_heights)
        if total_doc_height <= 0:
            return

        y_offsets = []
        curr_offset = 0
        for ph in self.page_heights:
            y_offsets.append(curr_offset)
            curr_offset += ph

        # Matches with more words (longer text overlaps) get brighter, thicker lines.
        # 30+ words = full intensity; 2-3 words = faint & thin.
        _MAX_REF_WORDS = 30

        painter = QPainter(self._lines_cache)
        for page_idx, matches in self.matches.items():
            if page_idx >= len(y_offsets):
                continue
            page_base_y = y_offsets[page_idx]
            for m in matches:
                if m.ignored:
                    continue
                confidence = m.confidence
                if confidence < self.min_confidence:
                    continue
                r = m.rect
                y_pixel = int(((page_base_y + r.y0) / total_doc_height) * h)

                # Weight by word count: small matches fade into the background
                word_count = len(m.source_data or [])
                weight = min(1.0, word_count / _MAX_REF_WORDS)
                alpha = int(40 + weight * 210)  # 40 (tiny) → 250 (large)
                line_width = max(1, round(1 + weight * 2))  # 1 px → 3 px

                # Red for critical (≥ 0.80), amber for informational
                if confidence >= 0.80:
                    color = QColor(243, 139, 168)
                else:
                    color = QColor(250, 170, 30)
                color.setAlpha(alpha)
                pen = QPen(color)
                pen.setWidth(line_width)
                painter.setPen(pen)
                painter.drawLine(2, y_pixel, w - 2, y_pixel)
        painter.end()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background gradient
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, QColor(30, 30, 46))
        gradient.setColorAt(1, QColor(24, 24, 37))
        painter.fillRect(self.rect(), gradient)

        if self.total_pages <= 0 or not self.page_heights:
            return

        h = self.height()

        # Build cache on first paint after data/resize change
        if self._lines_cache is None:
            self._build_lines_cache()

        # Blit the pre-rendered match markers (single drawPixmap, no per-match work)
        if self._lines_cache is not None:
            painter.drawPixmap(0, 0, self._lines_cache)

        # Viewport indicator — only dynamic element, drawn fresh each frame
        painter.setPen(QPen(QColor(205, 214, 244, 100), 1))
        painter.setBrush(QColor(205, 214, 244, 30))
        vy = int(self.viewport_pos * h)
        vh = max(int(self.viewport_height * h), 10)
        painter.drawRoundedRect(2, vy, self.width() - 4, vh, 3, 3)

    def mousePressEvent(self, event):
        self.clicked.emit(event.position().y() / self.height())
