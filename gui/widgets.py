from PyQt6.QtWidgets import (
    QListWidget,
    QLabel,
    QWidget,
    QListWidgetItem,
    QMenu,
    QApplication,
)
from PyQt6.QtGui import QPainter, QColor, QMouseEvent, QAction, QCursor
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
import os
import fitz


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
    matchIgnored = pyqtSignal(object)  # Signal to ignore a match (passed match object)

    def __init__(self, pixmap, highlights, color_map, scale_factor=1.0):
        super().__init__()
        self.original_pixmap = pixmap
        self.highlights = highlights
        self.color_map = color_map
        self.scale_factor = scale_factor
        self.setPixmap(self.original_pixmap)
        self.draw_highlights()
        self.setMouseTracking(True)

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
        matches_here = []
        for h in self.highlights:
            if h.get("ignored", False):
                continue
            r = h["rect"]
            if (r.x0 <= x <= r.x1) and (r.y0 <= y <= r.y1):
                matches_here.append(h)
        if matches_here:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            sources = set(
                os.path.basename(m.get("source", "Unknown")) for m in matches_here
            )
            count = len(matches_here)
            if count > 1:
                self.setToolTip(f"{count} Matches: {', '.join(sources)}")
            else:
                self.setToolTip(f"Source: {list(sources)[0]}")
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setToolTip("")
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
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

        # Find match under cursor
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
