"""
Main Application Window for PDFCompare.

This module provides the primary UI controller that integrates:
- Document comparison workflow management
- PDF rendering via the PDFRenderer engine
- Match navigation and visualization
- Modern dark theme styling
"""

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
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtCore import Qt, QThread, QTimer

from compare_logic import PDFComparator
from gui.widgets import FileListWidget, PDFPageLabel, MiniMapWidget
from gui.workers import CompareWorker, IndexWorker
from gui.pdf_renderer import PDFRenderer


# ============================================================================
# Modern Color Palette (Catppuccin-inspired)
# ============================================================================
class Theme:
    """Modern dark theme color definitions."""

    # Base colors
    BASE = "#1e1e2e"
    MANTLE = "#181825"
    CRUST = "#11111b"
    SURFACE0 = "#313244"
    SURFACE1 = "#45475a"
    SURFACE2 = "#585b70"

    # Text colors
    TEXT = "#cdd6f4"
    SUBTEXT1 = "#bac2de"
    SUBTEXT0 = "#a6adc8"
    OVERLAY2 = "#9399b2"
    OVERLAY1 = "#7f849c"
    OVERLAY0 = "#6c7086"

    # Accent colors
    LAVENDER = "#b4befe"
    BLUE = "#89b4fa"
    SAPPHIRE = "#74c7ec"
    SKY = "#89dceb"
    TEAL = "#94e2d5"
    GREEN = "#a6e3a1"
    YELLOW = "#f9e2af"
    PEACH = "#fab387"
    MAROON = "#eba0ac"
    RED = "#f38ba8"
    MAUVE = "#cba6f7"
    PINK = "#f5c2e7"
    FLAMINGO = "#f2cdcd"
    ROSEWATER = "#f5e0dc"

    # Highlight colors (with alpha)
    HIGHLIGHT_COLORS = [
        QColor(243, 139, 168, 80),  # Red
        QColor(166, 227, 161, 80),  # Green
        QColor(137, 180, 250, 80),  # Blue
        QColor(249, 226, 175, 80),  # Yellow
        QColor(203, 166, 247, 80),  # Mauve
        QColor(148, 226, 213, 80),  # Teal
        QColor(250, 179, 135, 80),  # Peach
        QColor(180, 190, 254, 80),  # Lavender
    ]


class MainWindow(QMainWindow):
    """
    Main application window for PDFCompare.

    Handles:
    - Layout and widget initialization
    - User interaction and state management
    - Rendering coordination via PDFRenderer
    - Theme application
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDFCompare")
        self.resize(1600, 900)
        self.apply_modern_theme()
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready. Drag and drop PDFs to start.")

        # Core components
        self.comparator = PDFComparator()
        self.target_renderer = PDFRenderer(cache_size=100)
        self.source_renderer = PDFRenderer(cache_size=50)
        self.process = psutil.Process(os.getpid())

        # Color mapping for sources
        self.color_map = {}
        self.colors = Theme.HIGHLIGHT_COLORS

        # State
        self.zoom_level = 1.2
        self.last_rendered_source = None
        self.last_rendered_zoom = None
        self.current_results = {}
        self.current_target_file = None
        self.ignored_match_ids = set()
        self.current_match_list = []
        self.current_match_index = 0

        self.init_ui()

        # Update stats frequently
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(2000)  # Every 2 seconds

    def apply_modern_theme(self):
        """Apply modern Catppuccin-inspired dark theme."""
        palette = QPalette()

        # Window and base colors
        palette.setColor(QPalette.ColorRole.Window, QColor(Theme.BASE))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(Theme.TEXT))
        palette.setColor(QPalette.ColorRole.Base, QColor(Theme.MANTLE))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(Theme.SURFACE0))

        # Text colors
        palette.setColor(QPalette.ColorRole.Text, QColor(Theme.TEXT))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(Theme.SURFACE0))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(Theme.TEXT))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(Theme.OVERLAY0))

        # Button colors
        palette.setColor(QPalette.ColorRole.Button, QColor(Theme.SURFACE0))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(Theme.TEXT))

        # Highlight
        palette.setColor(QPalette.ColorRole.Highlight, QColor(Theme.MAUVE))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(Theme.CRUST))

        # Links
        palette.setColor(QPalette.ColorRole.Link, QColor(Theme.BLUE))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor(Theme.LAVENDER))

        # Bright text for warnings
        palette.setColor(QPalette.ColorRole.BrightText, QColor(Theme.RED))

        QApplication.setPalette(palette)

        # Global stylesheet for additional styling
        QApplication.instance().setStyleSheet(f"""
            QMainWindow {{
                background-color: {Theme.BASE};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {Theme.SURFACE1};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
                background-color: {Theme.MANTLE};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {Theme.LAVENDER};
            }}
            QSpinBox, QComboBox {{
                background-color: {Theme.SURFACE0};
                border: 1px solid {Theme.SURFACE1};
                border-radius: 6px;
                padding: 4px 8px;
                color: {Theme.TEXT};
                min-height: 24px;
            }}
            QSpinBox:hover, QComboBox:hover {{
                border-color: {Theme.MAUVE};
            }}
            QSpinBox:focus, QComboBox:focus {{
                border-color: {Theme.LAVENDER};
            }}
            QPushButton {{
                background-color: {Theme.SURFACE0};
                border: 1px solid {Theme.SURFACE1};
                border-radius: 6px;
                padding: 6px 14px;
                color: {Theme.TEXT};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE1};
                border-color: {Theme.MAUVE};
            }}
            QPushButton:pressed {{
                background-color: {Theme.SURFACE2};
            }}
            QPushButton:disabled {{
                background-color: {Theme.SURFACE0};
                color: {Theme.OVERLAY0};
            }}
            QCheckBox {{
                spacing: 8px;
                color: {Theme.TEXT};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid {Theme.SURFACE2};
                background-color: {Theme.SURFACE0};
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.MAUVE};
                border-color: {Theme.MAUVE};
            }}
            QCheckBox::indicator:hover {{
                border-color: {Theme.LAVENDER};
            }}
            QScrollArea {{
                border: none;
                background-color: {Theme.MANTLE};
            }}
            QScrollBar:vertical {{
                background-color: {Theme.MANTLE};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Theme.SURFACE1};
                border-radius: 5px;
                min-height: 30px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {Theme.SURFACE2};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QProgressBar {{
                border: none;
                border-radius: 6px;
                background-color: {Theme.SURFACE0};
                text-align: center;
                color: {Theme.TEXT};
            }}
            QProgressBar::chunk {{
                background-color: {Theme.GREEN};
                border-radius: 6px;
            }}
            QTextEdit {{
                background-color: {Theme.MANTLE};
                border: 1px solid {Theme.SURFACE1};
                border-radius: 8px;
                color: {Theme.TEXT};
                selection-background-color: {Theme.MAUVE};
            }}
            QLabel {{
                color: {Theme.TEXT};
            }}
            QStatusBar {{
                background-color: {Theme.CRUST};
                color: {Theme.SUBTEXT0};
            }}
            QSplitter::handle {{
                background-color: {Theme.SURFACE0};
            }}
            QSplitter::handle:horizontal {{
                width: 3px;
            }}
        """)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(8)

        # Algorithm Parameters Group
        gb_config = QGroupBox("Algorithm Parameters")
        gb_layout = QVBoxLayout()
        gb_layout.setSpacing(6)

        lbl_phase_a = QLabel("<b>Phase A: Matching</b>")
        lbl_phase_a.setStyleSheet(f"color: {Theme.LAVENDER}; font-size: 11px;")
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
        lbl_phase_b.setStyleSheet(f"color: {Theme.LAVENDER}; font-size: 11px;")
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

        # Reference Files
        left_layout.addWidget(QLabel("Reference PDFs:"))
        self.reference_list = FileListWidget("References")
        left_layout.addWidget(self.reference_list)

        btn_clr_ref = QPushButton("Clear References")
        btn_clr_ref.clicked.connect(self.reference_list.clear)
        left_layout.addWidget(btn_clr_ref)

        left_layout.addSpacing(10)

        # Target File
        left_layout.addWidget(QLabel("Target PDF:"))
        self.target_list = FileListWidget("Target")
        self.target_list.setMaximumHeight(80)
        left_layout.addWidget(self.target_list)

        btn_clr_tgt = QPushButton("Clear Target")
        btn_clr_tgt.clicked.connect(self.target_list.clear)
        left_layout.addWidget(btn_clr_tgt)

        left_layout.addSpacing(10)

        # Run Button
        self.btn_run = QPushButton("▶  Run Comparison")
        self.btn_run.setFixedHeight(44)
        self.btn_run.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.GREEN};
                color: {Theme.CRUST};
                font-weight: bold;
                font-size: 13px;
                border-radius: 8px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {Theme.TEAL};
            }}
            QPushButton:pressed {{
                background-color: {Theme.SAPPHIRE};
            }}
            QPushButton:disabled {{
                background-color: {Theme.SURFACE1};
                color: {Theme.OVERLAY0};
            }}
        """)
        self.btn_run.clicked.connect(self.run_comparison)
        left_layout.addWidget(self.btn_run)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        left_layout.addWidget(self.progress_bar)

        left_layout.addSpacing(10)

        # Legend
        left_layout.addWidget(QLabel("Legend:"))
        self.legend_layout = QVBoxLayout()
        left_layout.addLayout(self.legend_layout)

        # Statistics
        left_layout.addStretch()
        gb_stats = QGroupBox("Statistics")
        self.stats_layout = QVBoxLayout()
        self.lbl_stats_ngrams = QLabel("N-Grams: 0")
        self.lbl_stats_mem = QLabel("Memory: 0 MB")
        self.lbl_stats_cache = QLabel("Cache: 0 pages")
        self.lbl_stats_mem.setToolTip(
            "Total Resident Set Size (RSS) of the application process."
        )
        self.stats_layout.addWidget(self.lbl_stats_ngrams)
        self.stats_layout.addWidget(self.lbl_stats_mem)
        self.stats_layout.addWidget(self.lbl_stats_cache)
        gb_stats.setLayout(self.stats_layout)
        left_layout.addWidget(gb_stats)

        # Shortcuts Indicator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"background-color: {Theme.SURFACE1};")
        left_layout.addWidget(line)

        lbl_shortcuts = QLabel(
            "<b>Shortcuts (Hover match):</b><br>Space: Next Match<br>Mouse Side: Back/Forward"
        )
        lbl_shortcuts.setStyleSheet(
            f"color: {Theme.OVERLAY1}; font-size: 10px; padding: 5px;"
        )
        left_layout.addWidget(lbl_shortcuts)

        # Middle Panel (Reference Viewer)
        middle_wrapper = QWidget()
        middle_layout = QVBoxLayout(middle_wrapper)
        middle_layout.setContentsMargins(0, 0, 0, 0)

        h_header = QHBoxLayout()
        self.lbl_source_title = QLabel("<b>Matched Reference Viewer</b>")
        h_header.addWidget(self.lbl_source_title)

        btn_zoom_in_s = QPushButton("+")
        btn_zoom_in_s.setFixedSize(28, 28)
        btn_zoom_in_s.setStyleSheet("font-size: 16px; font-weight: bold;")
        btn_zoom_in_s.clicked.connect(lambda: self.change_zoom(0.1))
        btn_zoom_out_s = QPushButton("-")
        btn_zoom_out_s.setFixedSize(28, 28)
        btn_zoom_out_s.setStyleSheet("font-size: 16px; font-weight: bold;")
        btn_zoom_out_s.clicked.connect(lambda: self.change_zoom(-0.1))
        h_header.addWidget(btn_zoom_out_s)
        h_header.addWidget(btn_zoom_in_s)
        h_header.addStretch()

        self.btn_prev_match = QPushButton("◀")
        self.btn_prev_match.setFixedSize(32, 28)
        self.btn_prev_match.clicked.connect(self.prev_match)
        self.btn_prev_match.setVisible(False)
        h_header.addWidget(self.btn_prev_match)

        self.lbl_match_counter = QLabel("")
        self.lbl_match_counter.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 11px;"
        )
        self.lbl_match_counter.setVisible(False)
        h_header.addWidget(self.lbl_match_counter)

        self.btn_next_match = QPushButton("▶")
        self.btn_next_match.setFixedSize(32, 28)
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
        self.source_text_edit.setStyleSheet(f"""
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-size: 12px;
            background-color: {Theme.MANTLE};
            color: {Theme.TEXT};
            border: none;
            padding: 12px;
        """)
        self.source_stack.addWidget(self.source_text_edit)
        middle_layout.addWidget(self.source_stack)

        # Right Panel (Target Viewer)
        right_wrapper = QWidget()
        right_main_layout = QVBoxLayout(right_wrapper)
        right_main_layout.setContentsMargins(0, 0, 0, 0)

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
        btn_zoom_in_t.setFixedSize(28, 28)
        btn_zoom_in_t.setStyleSheet("font-size: 16px; font-weight: bold;")
        btn_zoom_in_t.clicked.connect(lambda: self.change_zoom(0.1))
        btn_zoom_out_t = QPushButton("-")
        btn_zoom_out_t.setFixedSize(28, 28)
        btn_zoom_out_t.setStyleSheet("font-size: 16px; font-weight: bold;")
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

        # Splitter setup
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

        # Collect active files from legend
        active_files = set()
        for i in range(self.legend_layout.count()):
            w = self.legend_layout.itemAt(i).widget()
            if isinstance(w, QCheckBox) and w.isChecked():
                active_files.add(w.property("file_path"))

        # Filter results
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
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Phase A: Indexing references... %p%")

        self.comparator.seed_size = self.spin_seed.value()
        self.comparator.merge_distance = self.spin_merge.value()

        self.status_bar.showMessage("Phase A: Indexing references...")

        self.index_thread = QThread()
        self.index_worker = IndexWorker(self.comparator, rf)
        self.index_worker.moveToThread(self.index_thread)
        self.index_thread.started.connect(self.index_worker.run)
        self.index_worker.finished.connect(self.on_index_finished)
        self.index_worker.progress.connect(self.on_index_progress)
        self.index_thread.start()

    def on_index_progress(self, percent: int, message: str):
        """Handle progress updates from index worker."""
        # Scale index progress to 0-30% of total progress
        scaled_percent = int(percent * 0.3)
        self.progress_bar.setValue(scaled_percent)
        self.progress_bar.setFormat(f"Phase A: {message} ({scaled_percent}%)")
        self.status_bar.showMessage(f"Phase A: {message}")

    def on_index_finished(self):
        self.index_thread.quit()
        self.index_thread.wait()

        self.status_bar.showMessage("Phase B: Comparing document...")
        self.progress_bar.setValue(30)
        self.progress_bar.setFormat("Phase B: Comparing document... (30%)")

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
        self.compare_worker.progress.connect(self.on_compare_progress)
        self.compare_thread.start()

    def on_compare_progress(self, percent: int, message: str):
        """Handle progress updates from compare worker."""
        # Scale compare progress from 30-100% of total
        scaled_percent = 30 + int(percent * 0.7)
        self.progress_bar.setValue(scaled_percent)
        self.progress_bar.setFormat(f"Phase B: {message} ({scaled_percent}%)")
        self.status_bar.showMessage(f"Phase B: {message}")

    def on_compare_finished(self, results, total_words, source_stats):
        self.compare_thread.quit()
        self.compare_thread.wait()
        self.btn_run.setEnabled(True)
        self.progress_bar.setVisible(False)

        self.current_results = results
        self.current_target_file = self.target_list.get_files()[0]

        doc = fitz.open(self.current_target_file)
        self.current_total_pages = len(doc)
        self.current_page_heights = [p.rect.height for p in doc]
        doc.close()

        # Clear legend
        for i in reversed(range(self.legend_layout.count())):
            self.legend_layout.itemAt(i).widget().setParent(None)

        # Build color map
        rf = self.reference_list.get_files()
        for i, fp in enumerate(rf):
            self.color_map[fp] = self.colors[i % len(self.colors)]

        # Build legend sorted by match count
        for fp in sorted(rf, key=lambda x: source_stats.get(x, 0), reverse=True):
            color = self.color_map[fp]
            mc = source_stats.get(fp, 0)
            percentage = (mc / total_words * 100) if total_words > 0 else 0

            chk = QCheckBox(f"{os.path.basename(fp)}: {percentage:.1f}% ({mc} words)")
            chk.setChecked(True)
            chk.setProperty("file_path", fp)
            chk.stateChanged.connect(self.refresh_target_view)
            chk.setStyleSheet(f"""
                QCheckBox {{
                    padding: 8px;
                    border-radius: 6px;
                    background-color: rgba({color.red()}, {color.green()}, {color.blue()}, 60);
                    font-size: 11px;
                }}
                QCheckBox:hover {{
                    background-color: rgba({color.red()}, {color.green()}, {color.blue()}, 80);
                }}
            """)
            self.legend_layout.addWidget(chk)

        self.refresh_target_view()
        self.update_stats()
        self.status_bar.showMessage(
            f"Comparison complete. Found matches from {len(source_stats)} sources.",
            5000,
        )

    def update_stats(self):
        self.lbl_stats_mem.setText(
            f"Memory: {self.process.memory_info().rss / 1024 / 1024:.1f} MB"
        )
        self.lbl_stats_ngrams.setText(
            f"Indexed N-Grams: {self.comparator.get_stats()['total_ngrams']}"
        )
        cache_stats = self.target_renderer.get_cache_stats()
        source_cache_stats = self.source_renderer.get_cache_stats()
        total_cached = cache_stats["cached_pages"] + source_cache_stats["cached_pages"]
        self.lbl_stats_cache.setText(f"Cached Pages: {total_cached}")

    def render_target(self, file_path, results):
        """
        Render target document with cached pixmaps.
        """
        # Clear existing widgets properly
        while self.target_layout.count():
            item = self.target_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        doc = fitz.open(file_path)
        zoom = self.zoom_level

        for page_idx, page in enumerate(doc):
            # Use cached pixmap
            pixmap = self.target_renderer.get_cached_pixmap(file_path, page_idx, zoom)

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

            lbl = PDFPageLabel(pixmap, highlights, self.color_map)
            lbl.page_index = page_idx
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

            if self.current_match_list:
                if (
                    self.current_match_list[self.current_match_index].get("match_id")
                    == mid
                ):
                    # Clear source view
                    while self.source_layout.count():
                        w = self.source_layout.takeAt(0).widget()
                        if w:
                            w.deleteLater()
                    self.lbl_source_title.setText("<b>Matched Reference Viewer</b>")
                    self.current_match_list = []

    def handle_matches_clicked(self, matches):
        # Check if we clicked the same set of matches (overlapping area)
        current_ids = [m.get("match_id") for m in matches]
        last_ids = (
            [m.get("match_id") for m in self.current_match_list]
            if self.current_match_list
            else []
        )

        if current_ids == last_ids:
            # Same spot clicked, cycle next
            self.next_match()
        else:
            # New spot, reset
            self.current_match_list = matches
            self.current_match_index = 0
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
        if self.current_match_list:
            current_match = self.current_match_list[self.current_match_index]
            # Pass all matches for this source file, plus the current match index
            self.load_source_view(
                current_match["source"],
                current_match["source_data"],
                all_matches=self.current_match_list,
                current_match_idx=self.current_match_index,
            )

    def load_source_view(
        self,
        file_path,
        source_data,
        all_matches=None,
        current_match_idx=0,
    ):
        """
        Load and display a reference document with match highlighting.

        Args:
            file_path: Path to the source PDF
            source_data: Match location data for the current match
            all_matches: Optional list of all matches to show (for multi-match view)
            current_match_idx: Index of the current/active match in all_matches
        """
        if not source_data:
            return

        tp = source_data[0][0]
        self.lbl_source_title.setText(
            f"Viewing Reference: <b>{os.path.basename(file_path)}</b>"
        )
        self.status_bar.showMessage(
            f"Jumped to match in '{os.path.basename(file_path)}' (Page {tp + 1})", 5000
        )

        should_rerender = (
            file_path != self.last_rendered_source
            or self.zoom_level != self.last_rendered_zoom
        )

        if should_rerender:
            self.last_rendered_source = file_path
            self.last_rendered_zoom = self.zoom_level

            # Clear existing widgets properly
            while self.source_layout.count():
                item = self.source_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()

            doc = fitz.open(file_path)
            zoom = self.zoom_level
            full_text = ""

            for page_idx, page in enumerate(doc):
                # Use cached pixmap
                pixmap = self.source_renderer.get_cached_pixmap(
                    file_path, page_idx, zoom
                )

                lbl = PDFPageLabel(
                    pixmap,
                    [],
                    {},
                )
                lbl.page_index = page_idx
                self.source_layout.addWidget(lbl)
                self.source_layout.addSpacing(10)
                full_text += (
                    f"--- Page {page_idx + 1} ---\n" + page.get_text("text") + "\n\n"
                )

            doc.close()
            self.source_text_edit.setText(full_text)

        # Build highlights for all matches from this source
        zoom = self.zoom_level

        # Get base color for this source
        base_color = self.color_map.get(file_path, QColor(255, 255, 0, 80))

        # Current match: bright gold color (high confidence draws border automatically)
        current_color = QColor(255, 180, 50, 100)  # Bright gold

        # Other matches: subtle, muted version of base color
        other_color = QColor(
            base_color.red(), base_color.green(), base_color.blue(), 40
        )

        # Collect all source_data from all matches for this file
        all_highlights_by_page = {}  # {page_idx: [(rect, is_current), ...]}

        if all_matches:
            for match_idx, match in enumerate(all_matches):
                # Only process matches from the same source file
                if match.get("source") != file_path:
                    continue

                match_source_data = match.get("source_data", [])
                is_current = match_idx == current_match_idx

                for page_idx, rect, word in match_source_data:
                    if page_idx not in all_highlights_by_page:
                        all_highlights_by_page[page_idx] = []
                    all_highlights_by_page[page_idx].append((rect, is_current))
        else:
            # Fallback: just use the current source_data
            for page_idx, rect, word in source_data:
                if page_idx not in all_highlights_by_page:
                    all_highlights_by_page[page_idx] = []
                all_highlights_by_page[page_idx].append((rect, True))

        target_widget = None

        for i in range(self.source_layout.count()):
            w = self.source_layout.itemAt(i).widget()
            if not isinstance(w, PDFPageLabel):
                continue

            p_idx = w.page_index
            page_highlight_data = all_highlights_by_page.get(p_idx, [])

            # Separate current and other highlights
            current_rects = [r for r, is_curr in page_highlight_data if is_curr]
            other_rects = [r for r, is_curr in page_highlight_data if not is_curr]

            # Sort and merge rects
            def merge_rects(rects):
                if not rects:
                    return []
                rects = sorted(rects, key=lambda r: (r.y0, r.x0))
                merged = []
                curr = rects[0]
                for nxt in rects[1:]:
                    if (
                        max(0, min(curr.y1, nxt.y1) - max(curr.y0, nxt.y0))
                        > (curr.y1 - curr.y0) * 0.5
                        and nxt.x0 - curr.x1 < 30
                    ):
                        curr.x1 = max(curr.x1, nxt.x1)
                    else:
                        merged.append(curr)
                        curr = nxt
                merged.append(curr)
                return merged

            merged_current = merge_rects(current_rects)
            merged_other = merge_rects(other_rects)

            # Build highlight list with different sources for coloring
            highlights = []

            # Add other matches (subtle)
            for r in merged_other:
                highlights.append(
                    {
                        "rect": fitz.Rect(
                            r.x0 * zoom, r.y0 * zoom, r.x1 * zoom, r.y1 * zoom
                        ),
                        "source": "OTHER_MATCH",
                        "confidence": 0.3,  # Low confidence for subtle rendering
                    }
                )

            # Add current match (prominent) - drawn last so it's on top
            for r in merged_current:
                highlights.append(
                    {
                        "rect": fitz.Rect(
                            r.x0 * zoom, r.y0 * zoom, r.x1 * zoom, r.y1 * zoom
                        ),
                        "source": "CURRENT_MATCH",
                        "confidence": 1.0,  # High confidence for prominent border
                    }
                )

            w.color_map = {
                "OTHER_MATCH": other_color,
                "CURRENT_MATCH": current_color,
            }
            w.highlights = highlights
            w.draw_highlights()

            if p_idx == tp:
                target_widget = w

        # Text Edit Highlighting
        doc_obj = self.source_text_edit.document()
        extra = []
        for p_idx in sorted(set(x[0] for x in source_data)):
            pw = [x[2] for x in source_data if x[0] == p_idx]
            hdr = f"--- Page {p_idx + 1} ---"
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
                        sel.format.setBackground(QColor(Theme.YELLOW))
                        sel.cursor = cur
                        extra.append(sel)
                        spos = cur.selectionEnd()
        self.source_text_edit.setExtraSelections(extra)

        # Scroll with delay to ensure layout is ready
        if target_widget:
            QTimer.singleShot(
                50, lambda: self.source_scroll.ensureWidgetVisible(target_widget)
            )
            hdr_to_find = f"--- Page {tp + 1} ---"
            cursor = doc_obj.find(hdr_to_find)
            if not cursor.isNull():
                QTimer.singleShot(
                    50, lambda: self.source_text_edit.setTextCursor(cursor)
                )
                QTimer.singleShot(
                    50, lambda: self.source_text_edit.ensureCursorVisible()
                )

    def closeEvent(self, event):
        """Clean up resources on window close."""
        self.target_renderer.cleanup()
        self.source_renderer.cleanup()
        super().closeEvent(event)
