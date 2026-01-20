import os
import psutil
import fitz
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QScrollArea,
    QMessageBox,
    QSpinBox,
    QGroupBox,
    QTextEdit,
    QStackedWidget,
    QCheckBox,
    QProgressBar,
    QComboBox,
    QApplication,
    QFrame,
)
from PyQt6.QtGui import QImage, QPixmap, QColor, QPalette
from PyQt6.QtCore import Qt, QThread, QTimer

from compare_logic import PDFComparator
from gui.widgets import FileListWidget, PDFPageLabel, MiniMapWidget
from gui.workers import CompareWorker, IndexWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDFCompare")
        self.resize(1600, 900)
        self.apply_dark_theme()
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready. Drag and drop PDFs to start.")
        self.comparator = PDFComparator()
        self.process = psutil.Process(os.getpid())
        self.color_map = {}
        self.colors = [
            QColor(255, 0, 0, 30),
            QColor(0, 255, 0, 30),
            QColor(0, 0, 255, 30),
            QColor(255, 255, 0, 30),
            QColor(255, 0, 255, 30),
            QColor(0, 255, 255, 30),
            QColor(255, 128, 0, 30),
            QColor(128, 0, 255, 30),
        ]
        self.zoom_level = 1.2
        self.init_ui()

        # Update stats frequently
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(2000)  # Every 2 seconds

    def apply_dark_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        QApplication.setPalette(palette)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        gb_config = QGroupBox("Algorithm Parameters")
        gb_layout = QVBoxLayout()
        lbl_phase_a = QLabel("<b>Phase A: Matching</b>")
        gb_layout.addWidget(lbl_phase_a)
        hbox_seed = QHBoxLayout()
        hbox_seed.addWidget(QLabel("Seed Size (words):"))
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(2, 10)
        self.spin_seed.setValue(3)
        hbox_seed.addWidget(self.spin_seed)
        gb_layout.addLayout(hbox_seed)
        hbox_merge = QHBoxLayout()
        hbox_merge.addWidget(QLabel("Merge Gap (words):"))
        self.spin_merge = QSpinBox()
        self.spin_merge.setRange(0, 100)
        self.spin_merge.setValue(15)
        hbox_merge.addWidget(self.spin_merge)
        gb_layout.addLayout(hbox_merge)
        hbox_mode = QHBoxLayout()
        hbox_mode.addWidget(QLabel("Compare Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Fast (Exact N-Gram)", "Fuzzy (Levenshtein)"])
        hbox_mode.addWidget(self.combo_mode)
        gb_layout.addLayout(hbox_mode)

        gb_layout.addSpacing(10)
        lbl_phase_b = QLabel("<b>Phase B: Refinement</b>")
        gb_layout.addWidget(lbl_phase_b)
        self.chk_sw_refinement = QCheckBox("Enable Smith-Waterman Refinement")
        self.chk_sw_refinement.setChecked(True)
        gb_layout.addWidget(self.chk_sw_refinement)
        hbox_expansion = QHBoxLayout()
        hbox_expansion.addWidget(QLabel("Context Lookahead:"))
        self.spin_expansion = QSpinBox()
        self.spin_expansion.setRange(0, 50)
        self.spin_expansion.setValue(1)
        hbox_expansion.addWidget(self.spin_expansion)
        gb_layout.addLayout(hbox_expansion)
        gb_config.setLayout(gb_layout)
        left_layout.addWidget(gb_config)

        left_layout.addWidget(QLabel("Reference PDFs:"))
        self.reference_list = FileListWidget("References")
        left_layout.addWidget(self.reference_list)
        btn_clr_ref = QPushButton("Clear")
        btn_clr_ref.clicked.connect(self.reference_list.clear)
        left_layout.addWidget(btn_clr_ref)

        left_layout.addSpacing(10)
        left_layout.addWidget(QLabel("Target PDF:"))
        self.target_list = FileListWidget("Target")
        self.target_list.setMaximumHeight(80)
        left_layout.addWidget(self.target_list)
        btn_clr_tgt = QPushButton("Clear")
        btn_clr_tgt.clicked.connect(self.target_list.clear)
        left_layout.addWidget(btn_clr_tgt)

        left_layout.addSpacing(10)
        self.btn_run = QPushButton("Run Comparison")
        self.btn_run.setFixedHeight(40)
        self.btn_run.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; border-radius: 5px;"
        )
        self.btn_run.clicked.connect(self.run_comparison)
        left_layout.addWidget(self.btn_run)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)

        self.current_results = {}
        self.current_target_file = None
        self.ignored_match_ids = set()

        left_layout.addSpacing(10)
        left_layout.addWidget(QLabel("Legend:"))
        self.legend_layout = QVBoxLayout()
        left_layout.addLayout(self.legend_layout)

        # 5. Statistics
        left_layout.addStretch()
        gb_stats = QGroupBox("Statistics")
        self.stats_layout = QVBoxLayout()
        self.lbl_stats_ngrams = QLabel("N-Grams: 0")
        self.lbl_stats_mem = QLabel("Memory: 0 MB")
        self.lbl_stats_mem.setToolTip(
            "Total Resident Set Size (RSS) of the application process."
        )
        self.stats_layout.addWidget(self.lbl_stats_ngrams)
        self.stats_layout.addWidget(self.lbl_stats_mem)
        gb_stats.setLayout(self.stats_layout)
        left_layout.addWidget(gb_stats)

        # 6. Shortcuts Indicator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #444;")
        left_layout.addWidget(line)

        lbl_shortcuts = QLabel(
            "<b>Shortcuts (Hover match):</b><br>Space: Next Match<br>Mouse Side: Back/Forward"
        )
        lbl_shortcuts.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
        left_layout.addWidget(lbl_shortcuts)

        # Middle Panel (Reference Viewer)
        middle_wrapper = QWidget()
        middle_layout = QVBoxLayout(middle_wrapper)
        h_header = QHBoxLayout()
        self.lbl_source_title = QLabel("<b>Matched Reference Viewer</b>")
        h_header.addWidget(self.lbl_source_title)
        btn_zoom_in_s = QPushButton("+")
        btn_zoom_in_s.setFixedSize(25, 25)
        btn_zoom_in_s.clicked.connect(lambda: self.change_zoom(0.1))
        btn_zoom_out_s = QPushButton("-")
        btn_zoom_out_s.setFixedSize(25, 25)
        btn_zoom_out_s.clicked.connect(lambda: self.change_zoom(-0.1))
        h_header.addWidget(btn_zoom_out_s)
        h_header.addWidget(btn_zoom_in_s)
        h_header.addStretch()
        self.btn_prev_match = QPushButton("<")
        self.btn_prev_match.setFixedSize(30, 25)
        self.btn_prev_match.clicked.connect(self.prev_match)
        self.btn_prev_match.setVisible(False)
        h_header.addWidget(self.btn_prev_match)
        self.lbl_match_counter = QLabel("")
        self.lbl_match_counter.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_match_counter.setVisible(False)
        h_header.addWidget(self.lbl_match_counter)
        self.btn_next_match = QPushButton(">")
        self.btn_next_match.setFixedSize(30, 25)
        self.btn_next_match.clicked.connect(self.next_match)
        self.btn_next_match.setVisible(False)
        h_header.addWidget(self.btn_next_match)
        h_header.addSpacing(10)
        self.btn_toggle_view = QPushButton("Switch to Text View")
        self.btn_toggle_view.setCheckable(True)
        self.btn_toggle_view.clicked.connect(self.toggle_source_view)
        h_header.addWidget(self.btn_toggle_view)
        middle_layout.addLayout(h_header)

        self.source_stack = QStackedWidget()
        self.source_scroll = QScrollArea()
        self.source_scroll.setWidgetResizable(True)
        self.source_container = QWidget()
        self.source_layout = QVBoxLayout(self.source_container)
        self.source_scroll.setWidget(self.source_container)
        self.source_stack.addWidget(self.source_scroll)
        self.source_text_edit = QTextEdit()
        self.source_text_edit.setReadOnly(True)
        self.source_text_edit.setStyleSheet(
            "font-family: monospace; font-size: 12px; background-color: #1e1e1e; color: #d4d4d4;"
        )
        self.source_stack.addWidget(self.source_text_edit)
        middle_layout.addWidget(self.source_stack)

        right_wrapper = QWidget()
        right_main_layout = QVBoxLayout(right_wrapper)
        h_right_head = QHBoxLayout()
        h_right_head.addWidget(
            QLabel("<b>Target Document</b> (Click highlights to trace)")
        )
        self.chk_hover = QCheckBox("Preview")
        self.chk_hover.setChecked(True)
        self.chk_hover.stateChanged.connect(self.toggle_hover_previews)
        h_right_head.addWidget(self.chk_hover)
        h_right_head.addStretch()
        btn_zoom_in_t = QPushButton("+")
        btn_zoom_in_t.setFixedSize(25, 25)
        btn_zoom_in_t.clicked.connect(lambda: self.change_zoom(0.1))
        btn_zoom_out_t = QPushButton("-")
        btn_zoom_out_t.setFixedSize(25, 25)
        btn_zoom_out_t.clicked.connect(lambda: self.change_zoom(-0.1))
        h_right_head.addWidget(btn_zoom_out_t)
        h_right_head.addWidget(btn_zoom_in_t)
        right_main_layout.addLayout(h_right_head)

        right_content_hbox = QHBoxLayout()
        self.target_scroll = QScrollArea()
        self.target_scroll.setWidgetResizable(True)
        self.target_container = QWidget()
        self.target_layout = QVBoxLayout(self.target_container)
        self.target_scroll.setWidget(self.target_container)
        right_content_hbox.addWidget(self.target_scroll)
        self.mini_map = MiniMapWidget()
        self.mini_map.clicked.connect(self.scroll_target_to_percent)
        right_content_hbox.addWidget(self.mini_map)
        right_main_layout.addLayout(right_content_hbox)
        self.target_scroll.verticalScrollBar().valueChanged.connect(
            self.update_mini_map_viewport
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(middle_wrapper)
        splitter.addWidget(right_wrapper)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)
        main_layout.addWidget(splitter)

    def change_zoom(self, delta):
        self.zoom_level = max(0.5, min(3.0, self.zoom_level + delta))
        self.status_bar.showMessage(f"Zoom Level: {self.zoom_level:.1f}x", 2000)
        self.refresh_target_view()
        self.load_current_match()

    def scroll_target_to_percent(self, percent):
        bar = self.target_scroll.verticalScrollBar()
        bar.setValue(int(percent * bar.maximum()))

    def update_mini_map_viewport(self):
        bar = self.target_scroll.verticalScrollBar()
        if bar.maximum() > 0:
            self.mini_map.set_viewport(
                bar.value() / bar.maximum(), bar.pageStep() / bar.maximum()
            )

    def toggle_hover_previews(self):
        state = self.chk_hover.isChecked()
        for i in range(self.target_layout.count()):
            w = self.target_layout.itemAt(i).widget()
            if isinstance(w, PDFPageLabel):
                w.show_hover_previews = state

    def toggle_source_view(self):
        self.source_stack.setCurrentIndex(1 if self.btn_toggle_view.isChecked() else 0)
        self.btn_toggle_view.setText(
            "Switch to PDF View"
            if self.btn_toggle_view.isChecked()
            else "Switch to Text View"
        )

    def refresh_target_view(self):
        if not self.current_results:
            return
        active_files = set()
        for i in range(self.legend_layout.count()):
            w = self.legend_layout.itemAt(i).widget()
            if isinstance(w, QCheckBox) and w.isChecked():
                active_files.add(w.property("file_path"))
        filtered = {}
        for p_idx, matches in self.current_results.items():
            fm = [
                m
                for m in matches
                if m["source"] in active_files
                and m["match_id"] not in self.ignored_match_ids
            ]
            if fm:
                filtered[p_idx] = fm
        self.render_target(self.current_target_file, filtered)
        self.mini_map.set_data(
            filtered,
            self.color_map,
            self.current_total_pages,
            getattr(self, "current_page_heights", None),
        )

    def run_comparison(self):
        rf, tf = self.reference_list.get_files(), self.target_list.get_files()
        if not rf or not tf:
            QMessageBox.warning(self, "Error", "Files missing.")
            return
        self.btn_run.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.comparator.seed_size, self.comparator.merge_distance = (
            self.spin_seed.value(),
            self.spin_merge.value(),
        )
        self.status_bar.showMessage("Indexing references...")
        self.index_thread = QThread()
        self.index_worker = IndexWorker(self.comparator, rf)
        self.index_worker.moveToThread(self.index_thread)
        self.index_thread.started.connect(self.index_worker.run)
        self.index_worker.finished.connect(self.on_index_finished)
        self.index_thread.start()

    def on_index_finished(self):
        self.index_thread.quit()
        self.index_thread.wait()
        self.status_bar.showMessage("Comparing document...")
        mode = "fast" if self.combo_mode.currentIndex() == 0 else "fuzzy"
        self.compare_thread = QThread()
        self.compare_worker = CompareWorker(
            self.comparator,
            self.target_list.get_files()[0],
            mode=mode,
            use_sw=self.chk_sw_refinement.isChecked(),
            sw_expansion=self.spin_expansion.value(),
        )
        self.compare_worker.moveToThread(self.compare_thread)
        self.compare_thread.started.connect(self.compare_worker.run)
        self.compare_worker.finished.connect(self.on_compare_finished)
        self.compare_thread.start()

    def on_compare_finished(self, results, total_words, source_stats):
        self.compare_thread.quit()
        self.compare_thread.wait()
        self.btn_run.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.current_results, self.current_target_file = (
            results,
            self.target_list.get_files()[0],
        )
        doc = fitz.open(self.current_target_file)
        self.current_total_pages, self.current_page_heights = (
            len(doc),
            [p.rect.height for p in doc],
        )
        doc.close()
        for i in reversed(range(self.legend_layout.count())):
            self.legend_layout.itemAt(i).widget().setParent(None)
        rf = self.reference_list.get_files()
        for i, fp in enumerate(rf):
            self.color_map[fp] = self.colors[i % len(self.colors)]
        for fp in sorted(rf, key=lambda x: source_stats.get(x, 0), reverse=True):
            color, mc = self.color_map[fp], source_stats.get(fp, 0)
            chk = QCheckBox(
                f"{os.path.basename(fp)}: {(mc / total_words * 100) if total_words > 0 else 0:.1f}% ({mc} words)"
            )
            chk.setChecked(True)
            chk.setProperty("file_path", fp)
            chk.stateChanged.connect(self.refresh_target_view)
            chk.setStyleSheet(
                f"QCheckBox {{ padding: 5px; border-radius: 3px; background-color: rgba({color.red()}, {color.green()}, {color.blue()}, 40); }}"
            )
            self.legend_layout.addWidget(chk)
        self.refresh_target_view()
        self.update_stats()

    def update_stats(self):
        self.lbl_stats_mem.setText(
            f"Memory: {self.process.memory_info().rss / 1024 / 1024:.1f} MB"
        )
        self.lbl_stats_ngrams.setText(
            f"Indexed N-Grams: {self.comparator.get_stats()['total_ngrams']}"
        )

    def render_target(self, file_path, results):
        while self.target_layout.count():
            w = self.target_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        doc = fitz.open(file_path)
        zoom = self.zoom_level
        mat = fitz.Matrix(zoom, zoom)
        for page_idx, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat)
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
            lbl = PDFPageLabel(
                QPixmap.fromImage(
                    QImage(
                        pix.samples,
                        pix.width,
                        pix.height,
                        pix.stride,
                        QImage.Format.Format_RGB888,
                    )
                ),
                highlights,
                self.color_map,
            )
            lbl.show_hover_previews = self.chk_hover.isChecked()
            lbl.matchesClicked.connect(self.handle_matches_clicked)
            lbl.matchIgnored.connect(self.handle_match_ignored)
            self.target_layout.addWidget(lbl)
            self.target_layout.addSpacing(10)
        doc.close()

    def handle_match_ignored(self, match):
        mid = match.get("match_id")
        if mid:
            self.ignored_match_ids.add(mid)
            self.status_bar.showMessage("Match block ignored.", 3000)
            self.refresh_target_view()
            if hasattr(self, "current_match_list") and self.current_match_list:
                if (
                    self.current_match_list[self.current_match_index].get("match_id")
                    == mid
                ):
                    while self.source_layout.count():
                        w = self.source_layout.takeAt(0).widget()
                        if w:
                            w.deleteLater()
                    self.lbl_source_title.setText("<b>Matched Reference Viewer</b>")
                    self.current_match_list = []

    def handle_matches_clicked(self, matches):
        self.current_match_list, self.current_match_index = matches, 0
        self.update_match_controls()
        self.load_current_match()

    def update_match_controls(self):
        c = len(self.current_match_list)
        if c > 1:
            self.btn_prev_match.setVisible(True)
            self.btn_next_match.setVisible(True)
            self.lbl_match_counter.setVisible(True)
            self.lbl_match_counter.setText(
                f"Match {self.current_match_index + 1} of {c}"
            )
        else:
            self.btn_prev_match.setVisible(False)
            self.btn_next_match.setVisible(False)
            self.lbl_match_counter.setVisible(False)

    def prev_match(self):
        if self.current_match_list:
            self.current_match_index = (self.current_match_index - 1) % len(
                self.current_match_list
            )
            self.update_match_controls()
            self.load_current_match()

    def next_match(self):
        if self.current_match_list:
            self.current_match_index = (self.current_match_index + 1) % len(
                self.current_match_list
            )
            self.update_match_controls()
            self.load_current_match()

    def load_current_match(self):
        if hasattr(self, "current_match_list") and self.current_match_list:
            self.load_source_view(
                self.current_match_list[self.current_match_index]["source"],
                self.current_match_list[self.current_match_index]["source_data"],
            )

    def load_source_view(self, file_path, source_data):
        if not source_data:
            return
        tp = source_data[0][0]
        self.lbl_source_title.setText(
            f"Viewing Reference: <b>{os.path.basename(file_path)}</b>"
        )
        self.status_bar.showMessage(
            f"Jumped to match in '{os.path.basename(file_path)}' (Page {tp + 1})", 5000
        )
        self.current_source_file = file_path
        while self.source_layout.count():
            w = self.source_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        doc = fitz.open(file_path)
        zoom, tw = self.zoom_level, None
        mat = fitz.Matrix(zoom, zoom)
        full_text = ""
        for page_idx, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat)
            pr = [x[1] for x in source_data if x[0] == page_idx]
            pr.sort(key=lambda r: (r.y0, r.x0))
            mr = []
            if pr:
                curr = pr[0]
                for nxt in pr[1:]:
                    if (
                        max(0, min(curr.y1, nxt.y1) - max(curr.y0, nxt.y0))
                        > (curr.y1 - curr.y0) * 0.5
                        and nxt.x0 - curr.x1 < 30
                    ):
                        curr.x1 = max(curr.x1, nxt.x1)
                    else:
                        mr.append(curr)
                        curr = nxt
                mr.append(curr)
            hl, color = [], self.color_map.get(file_path, QColor(255, 255, 0, 80))
            if color.alpha() < 60:
                color.setAlpha(60)
            for r in mr:
                hl.append(
                    {
                        "rect": fitz.Rect(
                            r.x0 * zoom, r.y0 * zoom, r.x1 * zoom, r.y1 * zoom
                        ),
                        "source": "SELECTION",
                    }
                )
            lbl = PDFPageLabel(
                QPixmap.fromImage(
                    QImage(
                        pix.samples,
                        pix.width,
                        pix.height,
                        pix.stride,
                        QImage.Format.Format_RGB888,
                    )
                ),
                hl,
                {"SELECTION": color},
            )
            self.source_layout.addWidget(lbl)
            self.source_layout.addSpacing(10)
            if page_idx == tp:
                tw = lbl
            full_text += (
                f"--- Page {page_idx + 1} ---\n" + page.get_text("text") + "\n\n"
            )
        doc.close()
        self.source_text_edit.setText(full_text)
        doc_obj, extra = self.source_text_edit.document(), []
        for p_idx in sorted(set(x[0] for x in source_data)):
            pw, hdr = (
                [x[2] for x in source_data if x[0] == p_idx],
                f"--- Page {p_idx + 1} ---",
            )
            start = doc_obj.find(hdr)
            if not start.isNull():
                for word in set(pw):
                    if len(word) < 3:
                        continue
                    spos = start.selectionEnd()
                    while True:
                        cur = doc_obj.find(word, spos)
                        if cur.isNull() or cur.position() > start.selectionEnd() + 5000:
                            break
                        sel = QTextEdit.ExtraSelection()
                        sel.format.setBackground(QColor(255, 255, 0, 100))
                        sel.cursor = cur
                        extra.append(sel)
                        spos = cur.selectionEnd()
        self.source_text_edit.setExtraSelections(extra)
        if tw:
            QApplication.instance().processEvents()
            self.source_scroll.ensureWidgetVisible(tw)
