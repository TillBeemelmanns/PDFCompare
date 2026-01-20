from PyQt6.QtWidgets import (
    QListWidget,
    QLabel,
    QWidget,
    QMenu,
    QVBoxLayout,
    QApplication,
)
from PyQt6.QtGui import QPainter, QColor, QMouseEvent, QAction, QImage, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QSize, QPoint
import fitz


class PreviewPopup(QWidget):
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
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.title = title
        self.setAlternatingRowColors(True)
        self.setStyleSheet("""
            QListWidget {
                border: 2px dashed #555;
                border-radius: 5px;
                background-color: #2b2b2b;
                color: #ddd;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #444;
                color: white;
            }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(
                "QListWidget { border: 2px dashed #4CAF50; background-color: #333; color: #ddd; }"
            )
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            QListWidget {
                border: 2px dashed #555;
                border-radius: 5px;
                background-color: #2b2b2b;
                color: #ddd;
                padding: 5px;
            }
        """)
        super().dragLeaveEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        self.setStyleSheet("""
            QListWidget {
                border: 2px dashed #555;
                border-radius: 5px;
                background-color: #2b2b2b;
                color: #ddd;
                padding: 5px;
            }
        """)
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(".pdf"):
                    self.addItem(file_path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def get_files(self):
        return [self.item(i).text() for i in range(self.count())]


class PDFPageLabel(QLabel):
    matchesClicked = pyqtSignal(list)
    matchIgnored = pyqtSignal(object)
    show_hover_previews = True

    _popup = None

    def __init__(self, pixmap, highlights, color_map, scale_factor=1.0):
        super().__init__()
        self.original_pixmap = pixmap
        self.highlights = highlights
        self.color_map = color_map
        self.scale_factor = scale_factor
        self.setPixmap(self.original_pixmap)
        self.draw_highlights()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.current_match_ids = []

        if PDFPageLabel._popup is None:
            PDFPageLabel._popup = PreviewPopup()

    def draw_highlights(self):
        if not self.highlights:
            self.setPixmap(self.original_pixmap)
            return
        canvas = self.original_pixmap.copy()
        painter = QPainter(canvas)
        for h in self.highlights:
            if h.get("ignored", False):
                continue
            source = h.get("source", "")
            rect = h["rect"]
            color = self.color_map.get(source, QColor(255, 0, 0, 40))
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            qrect = QRectF(rect.x0, rect.y0, rect.width, rect.height)
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
        if self._popup:
            self._popup.hide()
        self.current_match_ids = []
        super().leaveEvent(event)

    def load_image_previews(self, matches):
        self._popup.set_loading()
        pixmaps = []

        for match in matches:
            source_path = match.get("source")
            data = match.get("source_data")
            if not source_path or not data:
                continue

            page_idx = data[0][0]
            rects = [fitz.Rect(item[1]) for item in data if item[0] == page_idx]
            if not rects:
                continue

            bbox = rects[0]
            for r in rects[1:]:
                bbox |= r

            margin = 30
            bbox.x0 = max(0, bbox.x0 - margin)
            bbox.y0 = max(0, bbox.y0 - margin)
            bbox.x1 += margin
            bbox.y1 += margin

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
            doc.close()

        self._popup.set_images(pixmaps)
        QApplication.instance().processEvents()

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
    clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(25)
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
        painter.fillRect(self.rect(), QColor(25, 25, 25))
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
                color.setAlpha(200)
                painter.setPen(color)
                painter.drawLine(0, y_pixel, self.width(), y_pixel)
        painter.setPen(QColor(255, 255, 255, 80))
        painter.setBrush(QColor(255, 255, 255, 20))
        vy = int(self.viewport_pos * h)
        vh = int(self.viewport_height * h)
        painter.drawRect(0, vy, self.width() - 1, vh)

    def mousePressEvent(self, event):
        self.clicked.emit(event.position().y() / self.height())
