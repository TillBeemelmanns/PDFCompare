"""
Custom Qt Widgets for PDFCompare.

This module provides specialized widgets for the PDF comparison interface:
- PreviewPopup: Floating tooltip for match previews
- FileListWidget: Drag-and-drop file list with enhanced UX
- PDFPageLabel: PDF page display with highlight overlays
- MiniMapWidget: Document navigation heatmap
"""

from PyQt6.QtWidgets import (
    QListWidget,
    QLabel,
    QWidget,
    QMenu,
    QVBoxLayout,
    QGraphicsDropShadowEffect,
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
    """

    files_changed = pyqtSignal()  # Emitted when file list changes

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.title = title
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
        if event.mimeData().hasUrls():
            # Count valid PDFs
            urls = event.mimeData().urls()
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
        else:
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

        if event.mimeData().hasUrls():
            added = 0
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()

                # Handle directories
                pdfs = self._find_pdfs_recursive(file_path)
                for pdf_path in pdfs:
                    # Avoid duplicates
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
        else:
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
            text = f"Drop {self.title} PDF(s) here\nor drag folders"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

            painter.end()


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
    show_hover_previews = True

    _popup = None
    _pending_preview_worker = None  # Track current preview worker for cancellation

    def __init__(self, pixmap, highlights, color_map, scale_factor=1.0):
        super().__init__()
        self.original_pixmap = pixmap
        self.highlights = highlights
        self.color_map = color_map
        self.scale_factor = scale_factor
        self.page_index = 0
        self.setPixmap(self.original_pixmap)
        self.draw_highlights()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.current_match_ids = []
        self._preview_request_ids = []  # Track which match_ids we requested previews for

        if PDFPageLabel._popup is None:
            PDFPageLabel._popup = PreviewPopup()

    def draw_highlights(self):
        if not self.highlights:
            self.setPixmap(self.original_pixmap)
            return
        canvas = self.original_pixmap.copy()
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for h in self.highlights:
            if h.get("ignored", False):
                continue
            source = h.get("source", "")
            rect = h["rect"]
            base_color = self.color_map.get(source, QColor(255, 0, 0, 40))

            # Adjust opacity based on confidence (0.0-1.0)
            confidence = h.get("confidence", 0.7)
            # Map confidence to alpha: 30 (low) to 120 (high)
            alpha = int(30 + confidence * 90)
            color = QColor(
                base_color.red(), base_color.green(), base_color.blue(), alpha
            )

            painter.setBrush(color)
            qrect = QRectF(rect.x0, rect.y0, rect.width, rect.height)

            # Draw border for high-confidence matches (>80%)
            if confidence >= 0.8:
                border_color = QColor(
                    base_color.red(), base_color.green(), base_color.blue(), 200
                )
                pen = QPen(border_color)
                pen.setWidth(2)
                painter.setPen(pen)
            else:
                painter.setPen(Qt.PenStyle.NoPen)

            painter.drawRect(qrect)
        painter.end()
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
            if h.get("ignored", False):
                continue
            r = h["rect"]
            if (r.x0 <= x <= r.x1) and (r.y0 <= y <= r.y1):
                matches_here.append(h)

        if matches_here:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocus()  # Grab focus for key events
            mids = [m.get("match_id") for m in matches_here]

            if self.show_hover_previews:
                if mids != self.current_match_ids:
                    self.current_match_ids = mids
                    self.load_image_previews(matches_here)

                pop_pos = event.globalPosition().toPoint() + QPoint(20, 20)
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
        match_ids = [m.get("match_id") for m in matches]
        self._preview_request_ids = match_ids

        # Create worker
        worker = PreviewWorker(matches, self.color_map, match_ids)
        worker.signals.finished.connect(self._on_preview_loaded)
        worker.signals.error.connect(self._on_preview_error)

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

    def _on_preview_error(self, error_msg: str):
        """Handle preview generation error."""
        # Just hide the loading indicator on error
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
                if h.get("ignored", False):
                    continue
                r = h["rect"]
                if (r.x0 <= x <= r.x1) and (r.y0 <= y <= r.y1):
                    if "source_data" in h and h["source_data"]:
                        clicked.append(h)
            if clicked:
                self.matchesClicked.emit(clicked)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        pos = event.pos()
        x, y = pos.x(), pos.y()
        match_under_cursor = None
        for h in self.highlights:
            if h.get("ignored", False):
                continue
            r = h["rect"]
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
            menu.exec(event.globalPos())

    def ignore_match(self, match):
        match["ignored"] = True
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
        self.color_map = {}
        self.total_pages = 1
        self.page_heights = []
        self.viewport_pos = 0.0
        self.viewport_height = 0.1

    def set_data(self, matches, color_map, total_pages, page_heights=None):
        self.matches = matches
        self.color_map = color_map
        self.total_pages = max(1, total_pages)
        self.page_heights = page_heights or [800.0] * self.total_pages
        self.update()

    def set_viewport(self, pos, height):
        self.viewport_pos = pos
        self.viewport_height = height
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Modern gradient background
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, QColor(30, 30, 46))
        gradient.setColorAt(1, QColor(24, 24, 37))
        painter.fillRect(self.rect(), gradient)

        if self.total_pages <= 0 or not self.page_heights:
            return

        h = self.height()
        total_doc_height = sum(self.page_heights)
        if total_doc_height <= 0:
            return

        y_offsets = []
        curr_offset = 0
        for ph in self.page_heights:
            y_offsets.append(curr_offset)
            curr_offset += ph

        # Draw match markers
        for page_idx, matches in self.matches.items():
            if page_idx >= len(y_offsets):
                continue
            page_base_y = y_offsets[page_idx]
            for m in matches:
                if m.get("ignored", False):
                    continue
                r = m["rect"]
                abs_y_pts = page_base_y + r.y0
                y_pixel = int((abs_y_pts / total_doc_height) * h)

                color = QColor(self.color_map.get(m["source"], QColor(255, 0, 0)))
                color.setAlpha(220)

                # Draw slightly thicker lines for visibility
                pen = QPen(color)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(2, y_pixel, self.width() - 2, y_pixel)

        # Draw viewport indicator with modern styling
        painter.setPen(QPen(QColor(205, 214, 244, 100), 1))
        painter.setBrush(QColor(205, 214, 244, 30))
        vy = int(self.viewport_pos * h)
        vh = max(int(self.viewport_height * h), 10)
        painter.drawRoundedRect(2, vy, self.width() - 4, vh, 3, 3)

    def mousePressEvent(self, event):
        self.clicked.emit(event.position().y() / self.height())
