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
    QSlider,
)
from PyQt6.QtGui import QColor, QPalette, QPixmap
from PyQt6.QtCore import Qt, QThread, QTimer, QThreadPool

from compare_logic import (
    PDFComparator,
    _INDEX_CACHE_DIR,
    _IGNORE_PHRASES_FILE,
    _normalize_ignore_phrase,
)
from models import HighlightEntry
from gui.widgets import FileListWidget, PDFPageLabel, MiniMapWidget, SourcePanelWidget
from gui.workers import CompareWorker, IndexWorker, PageRenderWorker
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
        self.target_renderer = PDFRenderer(max_bytes=256 * 1024 * 1024)  # 256 MB
        self.source_renderer = PDFRenderer(max_bytes=128 * 1024 * 1024)  # 128 MB
        self.process = psutil.Process(os.getpid())

        # State
        self.zoom_level = 1.2
        self.last_rendered_source = None
        self.last_rendered_zoom = None
        self.current_results = {}
        self.current_target_file = None
        self.ignored_match_ids = set()
        self.current_match_list = []
        self.current_match_index = 0
        self.widget_pool = []  # Pool for PDFPageLabel reuse

        # Reference-viewer navigation: sorted list of reference page indices that
        # have highlight marks; _source_match_page_idx is the current position.
        self._source_match_pages: list = []
        self._source_match_page_idx: int = 0

        # Virtual scroll state — target view
        self._page_slots: list = []
        self._page_slot_data: list = []
        self._target_page_dims: list = []
        self._target_page_y_offsets: list = []
        self._target_virtual_file: str = None

        # Virtual scroll state — source view
        self._source_page_slots: list = []
        self._source_page_slot_data: list = []
        self._source_page_dims: list = []
        self._source_page_y_offsets: list = []
        self._source_virtual_file: str = None

        # Debounce timer — fires _do_refresh_target_view 150 ms after last call
        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(150)
        self._refresh_timer.timeout.connect(self._do_refresh_target_view)

        # Throttle timers — limit virtual scroll updates to ~20 fps
        self._virtual_scroll_timer = QTimer()
        self._virtual_scroll_timer.setSingleShot(True)
        self._virtual_scroll_timer.setInterval(50)
        self._virtual_scroll_timer.timeout.connect(self._update_visible_target_pages)

        self._source_scroll_timer = QTimer()
        self._source_scroll_timer.setSingleShot(True)
        self._source_scroll_timer.setInterval(50)
        self._source_scroll_timer.timeout.connect(self._update_visible_source_pages)

        # Background page-render pool (uncached pages while scrolling)
        self._bg_render_pool = QThreadPool()
        self._bg_render_pool.setMaxThreadCount(2)
        self._pending_bg_render_worker = None
        self._pending_bg_source_worker = None

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
        # Create the splitter as the primary layout element
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Left Panel — plain widget so stretch factors work (no outer scroll area)
        left_panel = QWidget()
        left_panel.setMinimumWidth(260)
        left_panel.setMaximumWidth(360)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(4)

        # Algorithm Parameters Group (compact)
        gb_config = QGroupBox("Algorithm Parameters")
        gb_layout = QVBoxLayout()
        gb_layout.setSpacing(3)
        gb_layout.setContentsMargins(6, 6, 6, 6)

        # Phase A row: seed + merge + mode packed tightly
        lbl_phase_a = QLabel("Phase A: Matching")
        lbl_phase_a.setStyleSheet(
            f"color: {Theme.LAVENDER}; font-size: 10px; font-weight: bold;"
        )
        gb_layout.addWidget(lbl_phase_a)

        row_seed = QHBoxLayout()
        row_seed.setSpacing(4)
        lbl_seed = QLabel("Seed:")
        lbl_seed.setStyleSheet("font-size: 11px;")
        lbl_seed.setToolTip("Minimum words that must match to form a candidate block.")
        row_seed.addWidget(lbl_seed)
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(2, 10)
        self.spin_seed.setValue(3)
        self.spin_seed.setFixedWidth(52)
        self.spin_seed.setToolTip(
            "Minimum number of consecutive words that must match to form a\n"
            "candidate block. Higher = fewer but more reliable matches."
        )
        row_seed.addWidget(self.spin_seed)
        lbl_merge = QLabel("Gap:")
        lbl_merge.setStyleSheet("font-size: 11px;")
        lbl_merge.setToolTip("Maximum word gap merged into one block.")
        row_seed.addWidget(lbl_merge)
        self.spin_merge = QSpinBox()
        self.spin_merge.setRange(0, 100)
        self.spin_merge.setValue(15)
        self.spin_merge.setFixedWidth(52)
        self.spin_merge.setToolTip(
            "Maximum word gap between two adjacent matches that will be\n"
            "merged into a single block. Higher = fewer, larger blocks."
        )
        row_seed.addWidget(self.spin_merge)
        gb_layout.addLayout(row_seed)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Fast (Exact N-Gram)", "Fuzzy (Levenshtein)"])
        self.combo_mode.setToolTip(
            "Fast: exact n-gram matching — best for identical or near-identical text.\n"
            "Fuzzy: Levenshtein distance allows minor typos and OCR errors (slower)."
        )
        gb_layout.addWidget(self.combo_mode)

        # Phase B row: SW checkbox + lookahead in one line
        lbl_phase_b = QLabel("Phase B: Refinement")
        lbl_phase_b.setStyleSheet(
            f"color: {Theme.LAVENDER}; font-size: 10px; font-weight: bold;"
        )
        gb_layout.addWidget(lbl_phase_b)

        row_sw = QHBoxLayout()
        row_sw.setSpacing(4)
        self.chk_sw_refinement = QCheckBox("Smith-Waterman")
        self.chk_sw_refinement.setChecked(True)
        self.chk_sw_refinement.setStyleSheet("font-size: 11px;")
        self.chk_sw_refinement.setToolTip(
            "Refines n-gram candidates with Smith-Waterman local alignment.\n"
            "Produces precise match boundaries and a confidence score (0–1).\n"
            "Disable for a faster but coarser result."
        )
        row_sw.addWidget(self.chk_sw_refinement, 1)
        lbl_exp = QLabel("Ctx:")
        lbl_exp.setStyleSheet("font-size: 11px;")
        lbl_exp.setToolTip("Context lookahead words beyond each n-gram boundary.")
        row_sw.addWidget(lbl_exp)
        self.spin_expansion = QSpinBox()
        self.spin_expansion.setRange(0, 50)
        self.spin_expansion.setValue(1)
        self.spin_expansion.setFixedWidth(52)
        self.spin_expansion.setToolTip(
            "Extra words inspected beyond each n-gram match boundary when\n"
            "running Smith-Waterman. Helps capture leading/trailing context\n"
            "that the n-gram phase may have clipped."
        )
        row_sw.addWidget(self.spin_expansion)
        gb_layout.addLayout(row_sw)

        gb_config.setLayout(gb_layout)
        left_layout.addWidget(gb_config)

        # Reference Files — create list first, then header row with inline clear button
        self.reference_list = FileListWidget("References")
        self.reference_list.setMinimumHeight(70)
        self.reference_list.setMaximumHeight(120)

        row_ref_hdr = QHBoxLayout()
        row_ref_hdr.setContentsMargins(0, 0, 0, 0)
        row_ref_hdr.addWidget(QLabel("Reference PDFs:"))
        row_ref_hdr.addStretch()
        btn_clr_ref = QPushButton("Clear")
        btn_clr_ref.setFixedHeight(22)
        btn_clr_ref.setStyleSheet("font-size: 10px; padding: 0 6px;")
        btn_clr_ref.clicked.connect(self.reference_list.clear)
        row_ref_hdr.addWidget(btn_clr_ref)
        left_layout.addLayout(row_ref_hdr)
        left_layout.addWidget(self.reference_list)

        # Target File — same pattern
        self.target_list = FileListWidget("Target", single_file=True)
        self.target_list.setFixedHeight(62)

        row_tgt_hdr = QHBoxLayout()
        row_tgt_hdr.setContentsMargins(0, 0, 0, 0)
        row_tgt_hdr.addWidget(QLabel("Target PDF:"))
        row_tgt_hdr.addStretch()
        btn_clr_tgt = QPushButton("Clear")
        btn_clr_tgt.setFixedHeight(22)
        btn_clr_tgt.setStyleSheet("font-size: 10px; padding: 0 6px;")
        btn_clr_tgt.clicked.connect(self.target_list.clear)
        row_tgt_hdr.addWidget(btn_clr_tgt)
        left_layout.addLayout(row_tgt_hdr)
        left_layout.addWidget(self.target_list)

        # Run Button
        self.btn_run = QPushButton("▶  Run Comparison")
        self.btn_run.setFixedHeight(36)
        self.btn_run.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.GREEN};
                color: {Theme.CRUST};
                font-weight: bold;
                font-size: 12px;
                border-radius: 6px;
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
        self.progress_bar.setFixedHeight(18)
        left_layout.addWidget(self.progress_bar)

        # Utility buttons — 2 per row to save vertical space
        row_util1 = QHBoxLayout()
        row_util1.setSpacing(4)
        self.btn_clear = QPushButton("✕  Clear Results")
        self.btn_clear.setEnabled(False)
        self.btn_clear.setFixedHeight(26)
        self.btn_clear.setStyleSheet("font-size: 11px;")
        self.btn_clear.setToolTip("Remove comparison results and reset both viewers.")
        self.btn_clear.clicked.connect(self.clear_results)
        row_util1.addWidget(self.btn_clear)

        btn_clear_cache = QPushButton("🗑  Cache")
        btn_clear_cache.setFixedHeight(26)
        btn_clear_cache.setStyleSheet("font-size: 11px;")
        btn_clear_cache.setToolTip(
            "Delete all cached reference index files from ~/.pdfcompare/index_cache/.\n"
            "Forces a full re-parse of reference PDFs on the next run."
        )
        btn_clear_cache.clicked.connect(self.clear_index_cache)
        row_util1.addWidget(btn_clear_cache)
        left_layout.addLayout(row_util1)

        btn_ignored = QPushButton("⊘  Edit Ignored Phrases")
        btn_ignored.setFixedHeight(26)
        btn_ignored.setStyleSheet("font-size: 11px;")
        btn_ignored.setToolTip(
            "Open ~/.pdfcompare/ignored_phrases.txt in your default text editor.\n"
            "One phrase per line. Changes take effect on the next Run Comparison."
        )
        btn_ignored.clicked.connect(self.open_ignored_phrases_file)
        left_layout.addWidget(btn_ignored)

        # Source panel — takes all remaining vertical space
        self.source_panel = SourcePanelWidget()
        self.source_panel.selection_changed.connect(self.refresh_target_view)
        self.source_panel.file_browse_requested.connect(self._browse_reference_pdf)
        left_layout.addWidget(self.source_panel, 1)

        # Statistics (compact — 2 lines)
        gb_stats = QGroupBox("Statistics")
        stats_grid = QHBoxLayout()
        stats_grid.setSpacing(8)
        self.lbl_stats_ngrams = QLabel("N-Grams: 0")
        self.lbl_stats_mem = QLabel("Memory: 0 MB")
        self.lbl_stats_cache = QLabel("Cache: 0 pages")
        self.lbl_stats_matches = QLabel("Matches: —")
        for lbl in (
            self.lbl_stats_ngrams,
            self.lbl_stats_mem,
            self.lbl_stats_cache,
            self.lbl_stats_matches,
        ):
            lbl.setStyleSheet("font-size: 10px;")
        self.lbl_stats_mem.setToolTip(
            "Total Resident Set Size (RSS) of the application process."
        )
        stats_col = QVBoxLayout()
        stats_col.setSpacing(1)
        row_s1 = QHBoxLayout()
        row_s1.addWidget(self.lbl_stats_ngrams)
        row_s1.addWidget(self.lbl_stats_mem)
        row_s2 = QHBoxLayout()
        row_s2.addWidget(self.lbl_stats_cache)
        row_s3 = QHBoxLayout()
        row_s3.addWidget(self.lbl_stats_matches)
        stats_col.addLayout(row_s1)
        stats_col.addLayout(row_s2)
        stats_col.addLayout(row_s3)
        gb_stats.setLayout(stats_col)
        left_layout.addWidget(gb_stats)

        # Middle Panel (Reference Viewer)
        middle_wrapper = QWidget()
        middle_layout = QVBoxLayout(middle_wrapper)
        middle_layout.setContentsMargins(0, 12, 0, 12)

        h_header = QHBoxLayout()
        h_header.setContentsMargins(12, 0, 12, 0)
        self.lbl_source_title = QLabel("<b>Matched Reference Viewer</b>")
        h_header.addWidget(self.lbl_source_title)

        btn_zoom_in_s = QPushButton("+")
        btn_zoom_in_s.setFixedSize(28, 28)
        btn_zoom_in_s.setStyleSheet("font-size: 16px; font-weight: bold; padding: 0px;")
        btn_zoom_in_s.clicked.connect(lambda: self.change_zoom(0.1))
        btn_zoom_out_s = QPushButton("-")
        btn_zoom_out_s.setFixedSize(28, 28)
        btn_zoom_out_s.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 0px;"
        )
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
        self.source_scroll.setWidget(self.source_container)
        self.source_scroll.verticalScrollBar().valueChanged.connect(
            self._on_source_scroll
        )
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
        right_main_layout.setContentsMargins(0, 12, 12, 12)

        h_right_head = QHBoxLayout()
        h_right_head.setContentsMargins(0, 0, 0, 0)
        h_right_head.addWidget(
            QLabel("<b>Target Document</b> (Click highlights to trace)")
        )

        self.chk_minimap = QCheckBox("Map")
        self.chk_minimap.setChecked(True)
        self.chk_minimap.stateChanged.connect(self._toggle_minimap)
        h_right_head.addWidget(self.chk_minimap)

        h_right_head.addStretch()

        # Highlight intensity slider (25 % – 200 %, default 100 %)
        lbl_intensity = QLabel("Intensity:")
        lbl_intensity.setStyleSheet("font-size: 11px;")
        h_right_head.addWidget(lbl_intensity)
        self.slider_intensity = QSlider(Qt.Orientation.Horizontal)
        self.slider_intensity.setRange(25, 200)
        self.slider_intensity.setValue(100)
        self.slider_intensity.setFixedWidth(80)
        self.slider_intensity.setToolTip(
            "Adjust highlight opacity (25 % – 200 %).\n"
            "Drag left for subtler highlights, right for more vivid."
        )
        self.slider_intensity.valueChanged.connect(self.on_hl_intensity_changed)
        h_right_head.addWidget(self.slider_intensity)
        self.lbl_intensity_val = QLabel("100%")
        self.lbl_intensity_val.setStyleSheet("font-size: 11px; min-width: 34px;")
        h_right_head.addWidget(self.lbl_intensity_val)
        h_right_head.addSpacing(6)

        # Minimum confidence slider (0 – 100 %, default 0 %)
        lbl_min_conf = QLabel("Min conf:")
        lbl_min_conf.setStyleSheet("font-size: 11px;")
        h_right_head.addWidget(lbl_min_conf)
        self.slider_min_conf = QSlider(Qt.Orientation.Horizontal)
        self.slider_min_conf.setRange(0, 100)
        self.slider_min_conf.setValue(0)
        self.slider_min_conf.setFixedWidth(80)
        self.slider_min_conf.setToolTip(
            "Minimum match confidence to display (0 % – 100 %).\n"
            "Increase to hide low-confidence matches and focus on\n"
            "near-identical text that may need rewriting."
        )
        self.slider_min_conf.valueChanged.connect(self.on_min_confidence_changed)
        h_right_head.addWidget(self.slider_min_conf)
        self.lbl_min_conf_val = QLabel("0%")
        self.lbl_min_conf_val.setStyleSheet("font-size: 11px; min-width: 34px;")
        h_right_head.addWidget(self.lbl_min_conf_val)
        h_right_head.addSpacing(6)

        btn_zoom_in_t = QPushButton("+")
        btn_zoom_in_t.setFixedSize(28, 28)
        btn_zoom_in_t.setStyleSheet("font-size: 16px; font-weight: bold; padding: 0px;")
        btn_zoom_in_t.clicked.connect(lambda: self.change_zoom(0.1))
        btn_zoom_out_t = QPushButton("-")
        btn_zoom_out_t.setFixedSize(28, 28)
        btn_zoom_out_t.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 0px;"
        )
        btn_zoom_out_t.clicked.connect(lambda: self.change_zoom(-0.1))
        h_right_head.addWidget(btn_zoom_out_t)
        h_right_head.addWidget(btn_zoom_in_t)
        right_main_layout.addLayout(h_right_head)

        right_content_hbox = QHBoxLayout()
        self.target_scroll = QScrollArea()
        self.target_scroll.setWidgetResizable(True)
        self.target_container = QWidget()
        self.target_scroll.setWidget(self.target_container)
        right_content_hbox.addWidget(self.target_scroll)

        self.mini_map = MiniMapWidget()
        self.mini_map.clicked.connect(self.scroll_target_to_percent)
        right_content_hbox.addWidget(self.mini_map)
        right_main_layout.addLayout(right_content_hbox)

        self.target_scroll.verticalScrollBar().valueChanged.connect(
            self._on_target_scroll
        )

        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(middle_wrapper)
        splitter.addWidget(right_wrapper)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)

    def change_zoom(self, delta):
        self.zoom_level = max(0.5, min(3.0, self.zoom_level + delta))
        self.status_bar.showMessage(f"Zoom Level: {self.zoom_level:.1f}x", 2000)
        self.refresh_target_view()
        self.load_current_match()

    def scroll_target_to_percent(self, percent):
        bar = self.target_scroll.verticalScrollBar()
        bar.setValue(int(percent * bar.maximum()))

    def update_mini_map_viewport(self):
        if not self.mini_map.isVisible():
            return
        bar = self.target_scroll.verticalScrollBar()
        if bar.maximum() > 0:
            self.mini_map.set_viewport(
                bar.value() / bar.maximum(), bar.pageStep() / bar.maximum()
            )

    def _toggle_minimap(self, state: int) -> None:
        visible = bool(state)
        self.mini_map.setVisible(visible)
        if visible:
            self.update_mini_map_viewport()

    def on_hl_intensity_changed(self, value: int) -> None:
        """Update global highlight intensity and redraw the target view."""
        PDFPageLabel.hl_intensity = value / 100.0
        self.lbl_intensity_val.setText(f"{value}%")
        # Invalidate all cached highlight renders so they pick up the new alpha
        for lbl in self._page_slots:
            lbl._hl_cache_key = None
            lbl.draw_highlights()

    def on_min_confidence_changed(self, value: int) -> None:
        """Update global minimum confidence and redraw target + minimap."""
        threshold = value / 100.0
        PDFPageLabel.min_confidence = threshold
        self.mini_map.min_confidence = threshold
        self.lbl_min_conf_val.setText(f"{value}%")
        # Invalidate highlight caches
        for lbl in self._page_slots:
            lbl._hl_cache_key = None
            lbl.draw_highlights()
        # Invalidate minimap
        self.mini_map._lines_cache = None
        self.mini_map.update()

    def toggle_source_view(self):
        self.source_stack.setCurrentIndex(1 if self.btn_toggle_view.isChecked() else 0)
        self.btn_toggle_view.setText(
            "Switch to PDF View"
            if self.btn_toggle_view.isChecked()
            else "Switch to Text View"
        )

    def refresh_target_view(self):
        """Debounced entry point — coalesces rapid calls (legend toggles, zoom) into one."""
        self._refresh_timer.start()

    def _do_refresh_target_view(self):
        if not self.current_results:
            return

        active_files = self.source_panel.get_active_files()

        # Filter results
        filtered = {}
        for p_idx, matches in self.current_results.items():
            fm = [
                m
                for m in matches
                if m.source in active_files and m.match_id not in self.ignored_match_ids
            ]
            if fm:
                filtered[p_idx] = fm

        saved_scroll = self.target_scroll.verticalScrollBar().value()
        self.render_target(
            self.current_target_file, filtered, restore_scroll=saved_scroll
        )
        self.mini_map.set_data(
            filtered,
            self.current_total_pages,
            getattr(self, "current_page_heights", None),
        )

    def _on_worker_error(self, title: str, message: str, thread: QThread) -> None:
        """Handle an error emitted by a background worker: stop thread, reset UI."""
        thread.quit()
        thread.wait()
        self.btn_run.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"{title}: {message}", 10000)
        QMessageBox.critical(self, title, message)

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
        self.index_worker.error.connect(
            lambda msg: self._on_worker_error("Indexing failed", msg, self.index_thread)
        )
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
        self.compare_worker.error.connect(
            lambda msg: self._on_worker_error(
                "Comparison failed", msg, self.compare_thread
            )
        )
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

        self.source_panel.populate(source_stats, total_words)

        self.btn_clear.setEnabled(True)

        n_matches = sum(len(m) for m in results.values())
        overlap_pct = (
            (sum(source_stats.values()) / total_words * 100) if total_words > 0 else 0.0
        )
        self.lbl_stats_matches.setText(
            f"Matches: {n_matches} blocks / {overlap_pct:.1f}% overlap"
        )

        self.refresh_target_view()
        self.update_stats()
        self.status_bar.showMessage(
            f"Done. {n_matches} match blocks from {len(source_stats)} source(s)"
            f" — {overlap_pct:.1f}% overlap.",
            8000,
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
        total_mb = (
            (cache_stats["used_bytes"] + source_cache_stats["used_bytes"]) / 1024 / 1024
        )
        self.lbl_stats_cache.setText(f"Cache: {total_cached} pages / {total_mb:.0f} MB")

    def render_target(self, file_path, results, restore_scroll=None):
        """
        Render target document using pixmap-swap lazy loading.

        All PDFPageLabel widgets stay in the layout permanently (stable layout,
        zero reflows during scroll). Materialization = set pixmap + draw highlights.
        Dematerialization = clear pixmap, releasing GPU/RAM for off-screen pages.
        """
        # Cancel any in-flight background render so stale results don't arrive
        if self._pending_bg_render_worker is not None:
            self._pending_bg_render_worker.cancel()
            self._pending_bg_render_worker = None

        # Pool existing page widgets for reuse
        for lbl in self._page_slots:
            lbl.setParent(None)
            lbl.hide()
            self.widget_pool.append(lbl)

        self._page_slots = []
        self._page_slot_data = []
        self._target_virtual_file = file_path

        zoom = self.zoom_level

        # One fitz open to get page dimensions (for fixed sizes)
        self._target_page_dims = self.target_renderer.get_page_dimensions(
            file_path, zoom
        )
        n_pages = len(self._target_page_dims)

        # Cumulative y-offsets for O(1) in-zone range checks during scroll
        self._target_page_y_offsets = []
        y = 0
        for _w, h in self._target_page_dims:
            self._target_page_y_offsets.append(y)
            y += h + 10  # matches addSpacing(10)

        # Pre-render first ~2 viewport heights in one fitz open
        vh = max(self.target_scroll.viewport().height(), 600)
        prerender_pages = [
            i for i, y_off in enumerate(self._target_page_y_offsets) if y_off < vh * 2
        ]
        self.target_renderer.batch_prerender(file_path, prerender_pages, zoom)

        # Create all page widgets and add them to the layout once.
        # Widgets stay in the layout forever; only their pixmaps are swapped.
        for page_idx in range(n_pages):
            highlights = []
            if page_idx in results:
                for m in results[page_idx]:
                    highlights.append(
                        HighlightEntry(
                            rect=fitz.Rect(
                                m.rect.x0 * zoom,
                                m.rect.y0 * zoom,
                                m.rect.x1 * zoom,
                                m.rect.y1 * zoom,
                            ),
                            source=m.source,
                            source_data=m.source_data,
                            match_id=m.match_id,
                            confidence=m.confidence,
                            match_density=m.match_density,
                        )
                    )

            w_px, h_px = self._target_page_dims[page_idx]
            if self.widget_pool:
                lbl = self.widget_pool.pop()
                try:
                    lbl.matchesClicked.disconnect()
                except (TypeError, RuntimeError):
                    pass
                try:
                    lbl.matchIgnored.disconnect()
                except (TypeError, RuntimeError):
                    pass
                try:
                    lbl.matchPhraseIgnored.disconnect()
                except (TypeError, RuntimeError):
                    pass
                lbl.original_pixmap = QPixmap()
                lbl.highlights = highlights
                lbl.color_map = {}
                lbl.setPixmap(QPixmap())
            else:
                lbl = PDFPageLabel(QPixmap(), highlights, {})

            lbl.page_index = page_idx
            lbl.matchesClicked.connect(self.handle_matches_clicked)
            lbl.matchIgnored.connect(self.handle_match_ignored)
            lbl.matchPhraseIgnored.connect(self.handle_phrase_ignored)
            # Fixed size keeps container geometry stable
            lbl.setFixedSize(int(w_px), int(h_px))
            # Parent to container but keep hidden; virtual scroll will
            # show + position only the pages near the viewport.
            lbl.setParent(self.target_container)

            self._page_slots.append(lbl)
            self._page_slot_data.append(
                {"highlights": highlights, "materialized": False}
            )

        # Set container height so the scrollbar covers all pages
        total_h = (
            int(self._target_page_y_offsets[-1] + self._target_page_dims[-1][1] + 10)
            if n_pages
            else 0
        )
        self.target_container.setMinimumHeight(total_h)

        # Let Qt finish the geometry pass, then materialize the visible pages.
        # If a scroll position was saved before the layout drain, restore it first
        # so the view doesn't jump to the top (or last widget) on refresh.
        if restore_scroll is not None:

            def _restore_and_materialize():
                self.target_scroll.verticalScrollBar().setValue(restore_scroll)
                self._update_visible_target_pages()

            QTimer.singleShot(0, _restore_and_materialize)
        else:
            QTimer.singleShot(0, self._update_visible_target_pages)

    def _on_target_scroll(self, value: int) -> None:
        """Called on every scroll-bar value change in the target view."""
        if self.mini_map.isVisible():
            self.update_mini_map_viewport()
        # Throttle: update visible pages at most once per 50 ms
        self._virtual_scroll_timer.start()

    def _update_visible_target_pages(self) -> None:
        """Materialize pages near the viewport; clear pixmaps of distant ones.

        Cached pages are materialized immediately on the main thread.
        Uncached pages are rendered off-thread by PageRenderWorker so the UI
        never blocks waiting for fitz rasterisation.
        """
        if not self._page_slots:
            return

        viewport_height = self.target_scroll.viewport().height()
        scroll_value = self.target_scroll.verticalScrollBar().value()

        render_top = max(0, scroll_value - viewport_height)
        render_bottom = scroll_value + 2 * viewport_height

        pages_in_zone: list[int] = []
        pages_out_of_zone: list[int] = []

        for i, (y_off, (_w, h)) in enumerate(
            zip(self._target_page_y_offsets, self._target_page_dims)
        ):
            if y_off + h >= render_top and y_off <= render_bottom:
                pages_in_zone.append(i)
            else:
                pages_out_of_zone.append(i)

        # Split in-zone pages into already-cached (instant) vs uncached (background)
        zoom_key = round(self.zoom_level, 2)
        cached_in_zone = [
            i
            for i in pages_in_zone
            if self.target_renderer.pixmap_cache.get(
                (self._target_virtual_file, i, zoom_key)
            )
            is not None
        ]
        uncached_in_zone = [i for i in pages_in_zone if i not in set(cached_in_zone)]

        # Materialize cached pages right now — zero blocking work
        for i in cached_in_zone:
            self._materialize_target_page(i)

        # Render uncached pages in a background thread
        if uncached_in_zone:
            if self._pending_bg_render_worker is not None:
                self._pending_bg_render_worker.cancel()
            worker = PageRenderWorker(
                self._target_virtual_file, uncached_in_zone, self.zoom_level
            )
            worker.signals.finished.connect(self._on_bg_pages_rendered)
            self._pending_bg_render_worker = worker
            self._bg_render_pool.start(worker)

        for i in pages_out_of_zone:
            self._dematerialize_target_page(i)

    def _on_bg_pages_rendered(self, results: list, zoom: float) -> None:
        """Main-thread callback: convert QImages → QPixmaps, store, materialise."""
        self._pending_bg_render_worker = None

        # Discard if the view has since been rebuilt at a different zoom / file
        if not self._page_slots or zoom != round(self.zoom_level, 2):
            return

        for page_idx, qimg in results:
            pixmap = QPixmap.fromImage(qimg)
            self.target_renderer.store_pixmap(
                self._target_virtual_file, page_idx, zoom, pixmap
            )

        # Materialise only pages still inside the visible buffer zone
        viewport_height = self.target_scroll.viewport().height()
        scroll_value = self.target_scroll.verticalScrollBar().value()
        render_top = max(0, scroll_value - viewport_height)
        render_bottom = scroll_value + 2 * viewport_height

        for page_idx, _ in results:
            if page_idx >= len(self._page_slot_data):
                continue
            y_off = self._target_page_y_offsets[page_idx]
            _w, h = self._target_page_dims[page_idx]
            if y_off + h >= render_top and y_off <= render_bottom:
                self._materialize_target_page(page_idx)

    def _materialize_target_page(self, page_idx: int) -> None:
        """Set the rendered pixmap on the page's PDFPageLabel and show it."""
        if self._page_slot_data[page_idx]["materialized"]:
            return
        lbl = self._page_slots[page_idx]
        pixmap = self.target_renderer.get_cached_pixmap(
            self._target_virtual_file, page_idx, self.zoom_level
        )
        lbl.original_pixmap = pixmap
        lbl.setFixedSize(pixmap.width(), pixmap.height())
        lbl.move(0, int(self._target_page_y_offsets[page_idx]))
        lbl.show()
        lbl.draw_highlights()
        self._page_slot_data[page_idx]["materialized"] = True

    def _dematerialize_target_page(self, page_idx: int) -> None:
        """Hide the page and clear its pixmap to free RAM."""
        if not self._page_slot_data[page_idx]["materialized"]:
            return
        lbl = self._page_slots[page_idx]
        lbl.hide()
        lbl.original_pixmap = QPixmap()
        lbl.setPixmap(QPixmap())
        lbl._hl_cache = None
        lbl._hl_cache_key = None
        self._page_slot_data[page_idx]["materialized"] = False

    def _on_source_scroll(self, value: int) -> None:
        """Called on every scroll-bar value change in the source view."""
        self._source_scroll_timer.start()

    def _update_visible_source_pages(self) -> None:
        """Materialize source pages near the viewport; clear pixmaps of distant ones.

        Cached pages are materialized immediately on the main thread.
        Uncached pages are rendered off-thread by PageRenderWorker so the UI
        never blocks waiting for fitz rasterisation.
        """
        if not self._source_page_slots:
            return

        viewport_height = self.source_scroll.viewport().height()
        scroll_value = self.source_scroll.verticalScrollBar().value()

        render_top = max(0, scroll_value - viewport_height)
        render_bottom = scroll_value + 2 * viewport_height

        pages_in_zone: list[int] = []
        pages_out_of_zone: list[int] = []

        for slot_idx, (y_off, (_w, h)) in enumerate(
            zip(self._source_page_y_offsets, self._source_page_dims)
        ):
            if y_off + h >= render_top and y_off <= render_bottom:
                pages_in_zone.append(slot_idx)
            else:
                pages_out_of_zone.append(slot_idx)

        # Split in-zone pages into already-cached (instant) vs uncached (background)
        zoom_key = round(self.zoom_level, 2)
        cached_in_zone = [
            i
            for i in pages_in_zone
            if self.source_renderer.pixmap_cache.get(
                (self._source_virtual_file, i, zoom_key)
            )
            is not None
        ]
        uncached_in_zone = [i for i in pages_in_zone if i not in set(cached_in_zone)]

        # Materialize cached pages right now — zero blocking work
        for i in cached_in_zone:
            self._materialize_source_page(i)

        # Render uncached pages in a background thread
        if uncached_in_zone:
            if self._pending_bg_source_worker is not None:
                self._pending_bg_source_worker.cancel()
            worker = PageRenderWorker(
                self._source_virtual_file, uncached_in_zone, self.zoom_level
            )
            worker.signals.finished.connect(self._on_bg_source_pages_rendered)
            self._pending_bg_source_worker = worker
            self._bg_render_pool.start(worker)

        for i in pages_out_of_zone:
            self._dematerialize_source_page(i)

    def _materialize_source_page(self, slot_idx: int) -> None:
        """Set the rendered pixmap on the source page's label and show it."""
        if self._source_page_slot_data[slot_idx]["materialized"]:
            return
        lbl = self._source_page_slots[slot_idx]
        pixmap = self.source_renderer.get_cached_pixmap(
            self._source_virtual_file, slot_idx, self.zoom_level
        )
        lbl.original_pixmap = pixmap
        lbl.setFixedSize(pixmap.width(), pixmap.height())
        lbl.move(0, int(self._source_page_y_offsets[slot_idx]))
        lbl.show()
        lbl.draw_highlights()
        self._source_page_slot_data[slot_idx]["materialized"] = True

    def _dematerialize_source_page(self, slot_idx: int) -> None:
        """Hide the source page and clear its pixmap to free RAM."""
        if not self._source_page_slot_data[slot_idx]["materialized"]:
            return
        lbl = self._source_page_slots[slot_idx]
        lbl.hide()
        lbl.original_pixmap = QPixmap()
        lbl.setPixmap(QPixmap())
        lbl._hl_cache = None
        lbl._hl_cache_key = None
        self._source_page_slot_data[slot_idx]["materialized"] = False

    def _on_bg_source_pages_rendered(self, results: list, zoom: float) -> None:
        """Main-thread callback: convert QImages → QPixmaps, store, materialise."""
        self._pending_bg_source_worker = None

        # Discard if the view has since been rebuilt at a different zoom / file
        if not self._source_page_slots or zoom != round(self.zoom_level, 2):
            return

        for page_idx, qimg in results:
            pixmap = QPixmap.fromImage(qimg)
            self.source_renderer.store_pixmap(
                self._source_virtual_file, page_idx, zoom, pixmap
            )

        # Materialise only pages still inside the visible buffer zone
        viewport_height = self.source_scroll.viewport().height()
        scroll_value = self.source_scroll.verticalScrollBar().value()
        render_top = max(0, scroll_value - viewport_height)
        render_bottom = scroll_value + 2 * viewport_height

        for page_idx, _ in results:
            if page_idx >= len(self._source_page_slot_data):
                continue
            y_off = self._source_page_y_offsets[page_idx]
            _w, h = self._source_page_dims[page_idx]
            if y_off + h >= render_top and y_off <= render_bottom:
                self._materialize_source_page(page_idx)

    def clear_results(self):
        """Reset both viewers and all comparison state without clearing file lists."""
        # Stop any in-flight work
        if self._pending_bg_render_worker is not None:
            self._pending_bg_render_worker.cancel()
            self._pending_bg_render_worker = None
        if self._pending_bg_source_worker is not None:
            self._pending_bg_source_worker.cancel()
            self._pending_bg_source_worker = None
        self._refresh_timer.stop()

        # Reset state
        self.current_results = {}
        self.current_target_file = None
        self.current_match_list = []
        self.current_match_index = 0
        self._source_match_pages = []
        self._source_match_page_idx = 0
        self.ignored_match_ids = set()
        self.last_rendered_source = None
        self.last_rendered_zoom = None
        self._page_slots = []
        self._page_slot_data = []
        self._source_page_slots = []
        self._source_page_slot_data = []

        # Delete all target page widgets and discard pool
        for lbl in self._page_slots:
            lbl.deleteLater()
        self.widget_pool.clear()
        self.target_container.setMinimumHeight(0)

        # Delete all source page widgets
        for lbl in self._source_page_slots:
            lbl.deleteLater()
        self.source_container.setMinimumHeight(0)

        self.source_panel.clear()
        self.source_panel.set_active_file(None)

        # Reset minimap
        self.mini_map.set_data({}, 1, None)

        # Hide match navigation controls
        self.btn_prev_match.setVisible(False)
        self.btn_next_match.setVisible(False)
        self.lbl_match_counter.setVisible(False)

        # Reset source title
        self.lbl_source_title.setText("<b>Matched Reference Viewer</b>")

        # Invalidate render caches
        self.target_renderer.invalidate_cache()
        self.source_renderer.invalidate_cache()

        # Update UI state
        self.btn_clear.setEnabled(False)
        self.lbl_stats_matches.setText("Matches: —")
        self.update_stats()
        self.status_bar.showMessage("Results cleared.", 3000)

    def load_files(self, target: str, refs: list, auto_run: bool = False) -> None:
        """Populate file lists from CLI arguments (called after the window is shown)."""
        for path in refs:
            if path not in self.reference_list.get_files():
                self.reference_list.addItem(path)
        if target and target not in self.target_list.get_files():
            self.target_list.addItem(target)
        if auto_run and target and refs:
            QTimer.singleShot(200, self.run_comparison)

    def open_ignored_phrases_file(self):
        """Open the ignored-phrases file in the system's default text editor."""
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl

        # Ensure the file exists so the editor opens something tangible
        _IGNORE_PHRASES_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _IGNORE_PHRASES_FILE.exists():
            _IGNORE_PHRASES_FILE.write_text(
                "# PDFCompare — globally ignored phrases\n"
                "# One phrase per line, case-insensitive.\n"
                "# Changes take effect on the next Run Comparison.\n",
                encoding="utf-8",
            )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(_IGNORE_PHRASES_FILE)))

    def clear_index_cache(self):
        """Delete all .pkl files from the on-disk reference index cache."""
        if not _INDEX_CACHE_DIR.exists():
            self.status_bar.showMessage("Index cache is already empty.", 3000)
            return
        files = list(_INDEX_CACHE_DIR.glob("*.pkl"))
        for f in files:
            f.unlink()
        self.status_bar.showMessage(
            f"Index cache cleared — {len(files)} file(s) removed.", 4000
        )

    def handle_phrase_ignored(self, match):
        """Persist the matched phrase to disk and immediately hide every block
        whose text contains the same phrase — not just the one right-clicked."""
        match_id = match.match_id
        if not match_id:
            return

        # Reconstruct the phrase from the clicked block (page-order word join).
        phrase_words = []
        for page_idx in sorted(self.current_results):
            for h in self.current_results[page_idx]:
                if h.match_id == match_id:
                    phrase_words.append(h.word)

        phrase = " ".join(phrase_words).strip().lower()
        if not phrase:
            return

        # Normalise the same way compare_document normalises block_text so the
        # substring check below is consistent with what happens on re-run.
        normalized = _normalize_ignore_phrase(phrase)

        # Collect words for every distinct match_id in the current results,
        # then suppress all blocks whose text contains the normalized phrase.
        match_words: dict = {}
        for page_idx in sorted(self.current_results):
            for h in self.current_results[page_idx]:
                mid = h.match_id
                if mid is not None:
                    match_words.setdefault(mid, []).append(h.word)

        newly_ignored = 0
        for mid, words in match_words.items():
            block_text = " ".join(w.lower() for w in words)
            if normalized in block_text:
                self.ignored_match_ids.add(mid)
                newly_ignored += 1

        # Append to the ignore file (create it and its parent dir if needed).
        _IGNORE_PHRASES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _IGNORE_PHRASES_FILE.open("a", encoding="utf-8") as f:
            f.write(phrase + "\n")

        self.status_bar.showMessage(
            f'Ignored "{phrase[:60]}{"…" if len(phrase) > 60 else ""}" '
            f"— {newly_ignored} block(s) suppressed.",
            5000,
        )
        self.refresh_target_view()

    def handle_match_ignored(self, match):
        mid = match.match_id
        if mid:
            self.ignored_match_ids.add(mid)
            self.status_bar.showMessage("Match block ignored.", 3000)
            self.refresh_target_view()

            if self.current_match_list:
                if self.current_match_list[self.current_match_index].match_id == mid:
                    # Clear source view
                    for w in self._source_page_slots:
                        w.deleteLater()
                    self._source_page_slots = []
                    self._source_page_slot_data = []
                    self.source_container.setMinimumHeight(0)
                    self.lbl_source_title.setText("<b>Matched Reference Viewer</b>")
                    self.current_match_list = []

    def handle_matches_clicked(self, matches):
        current_ids = [m.match_id for m in matches]
        last_ids = (
            [m.match_id for m in self.current_match_list]
            if self.current_match_list
            else []
        )
        if current_ids == last_ids:
            # Same spot re-clicked: advance to the next highlighted page in the
            # reference viewer (cycles through all matches from that source file).
            self.next_match()
        else:
            self.current_match_list = matches
            self.current_match_index = 0
            self.load_current_match()

    def update_match_controls(self):
        """Show/hide ◀▶ navigation based on how many reference pages are highlighted."""
        n = len(self._source_match_pages)
        if n > 1:
            self.btn_prev_match.setVisible(True)
            self.btn_next_match.setVisible(True)
            self.lbl_match_counter.setVisible(True)
            self.lbl_match_counter.setText(
                f"Match {self._source_match_page_idx + 1} of {n}"
            )
        else:
            self.btn_prev_match.setVisible(False)
            self.btn_next_match.setVisible(False)
            self.lbl_match_counter.setVisible(False)

    def _scroll_to_source_match(self):
        """Scroll the reference viewer to _source_match_pages[_source_match_page_idx]."""
        if not self._source_match_pages or not self._source_page_slots:
            return
        page_idx = self._source_match_pages[self._source_match_page_idx]
        if page_idx < len(self._source_page_y_offsets):
            self.source_scroll.verticalScrollBar().setValue(
                int(self._source_page_y_offsets[page_idx])
            )
        n = len(self._source_match_pages)
        self.status_bar.showMessage(
            f"Reference match {self._source_match_page_idx + 1} of {n}", 3000
        )

    def prev_match(self):
        if not self._source_match_pages:
            return
        self._source_match_page_idx = (self._source_match_page_idx - 1) % len(
            self._source_match_pages
        )
        self._scroll_to_source_match()
        self.update_match_controls()

    def next_match(self):
        if not self._source_match_pages:
            return
        self._source_match_page_idx = (self._source_match_page_idx + 1) % len(
            self._source_match_pages
        )
        self._scroll_to_source_match()
        self.update_match_controls()

    def load_current_match(self):
        if self.current_match_list:
            current_match = self.current_match_list[self.current_match_index]
            self.load_source_view(
                current_match.source,
                current_match.source_data,
            )

    def _browse_reference_pdf(self, file_path: str) -> None:
        """Open a reference PDF in the viewer without jumping to a specific match."""
        self.current_match_list = []
        self.current_match_index = 0
        self.load_source_view(file_path, source_data=[])

    def load_source_view(self, file_path, source_data):
        """
        Load and display a reference document with match highlighting.

        Highlights ALL matches from this source file (from current_results) so the
        user can cycle through them with repeated clicks or the ◀▶ buttons.
        The specific match given by source_data is shown in gold; all others amber.

        Args:
            file_path:   Path to the source PDF
            source_data: (page, rect, word) triples for the currently-active match
                         (empty list when browsing without a specific match)
        """
        tp = source_data[0][0] if source_data else None
        name = os.path.basename(file_path)
        display_name = name if len(name) <= 40 else name[:37] + "…"
        self.lbl_source_title.setText(f"Viewing Reference: <b>{display_name}</b>")
        self.lbl_source_title.setToolTip(file_path)
        self.source_panel.set_active_file(file_path)
        if tp is not None:
            self.status_bar.showMessage(
                f"Jumped to match in '{os.path.basename(file_path)}' (Page {tp + 1})",
                5000,
            )
        else:
            self.status_bar.showMessage(
                f"Browsing reference: '{os.path.basename(file_path)}'", 3000
            )

        should_rerender = (
            file_path != self.last_rendered_source
            or self.zoom_level != self.last_rendered_zoom
        )

        if should_rerender:
            if self._pending_bg_source_worker is not None:
                self._pending_bg_source_worker.cancel()
                self._pending_bg_source_worker = None

            self.last_rendered_source = file_path
            self.last_rendered_zoom = self.zoom_level

            # Pool existing source page widgets for reuse
            for lbl in self._source_page_slots:
                lbl.setParent(None)
                lbl.hide()
                self.widget_pool.append(lbl)

            self._source_page_slots = []
            self._source_page_slot_data = []
            self._source_virtual_file = file_path

            doc = fitz.open(file_path)
            zoom = self.zoom_level
            zoom_key = round(zoom, 2)

            # Compute page dims from the already-open doc (avoids a second fitz.open)
            self._source_page_dims = [
                (p.rect.width * zoom_key, p.rect.height * zoom_key) for p in doc
            ]

            self._source_page_y_offsets = []
            y = 0
            for _w, h in self._source_page_dims:
                self._source_page_y_offsets.append(y)
                y += h + 10

            # Pre-render: first viewport + target page area (all while doc is open)
            vh = max(self.source_scroll.viewport().height(), 600)
            tp_y = (
                self._source_page_y_offsets[tp]
                if tp is not None and tp < len(self._source_page_y_offsets)
                else 0
            )
            prerender_pages = list(
                {
                    i
                    for i, y_off in enumerate(self._source_page_y_offsets)
                    if y_off < vh * 2 or abs(y_off - tp_y) < vh * 1.5
                }
            )
            self.source_renderer.batch_prerender(file_path, prerender_pages, zoom, doc)

            # Build all widgets with empty pixmaps + fixed sizes; extract text
            full_text = ""
            for page_idx, page in enumerate(doc):
                w_px, h_px = self._source_page_dims[page_idx]

                if self.widget_pool:
                    lbl = self.widget_pool.pop()
                    try:
                        lbl.matchesClicked.disconnect()
                    except (TypeError, RuntimeError):
                        pass
                    try:
                        lbl.matchIgnored.disconnect()
                    except (TypeError, RuntimeError):
                        pass
                    try:
                        lbl.matchPhraseIgnored.disconnect()
                    except (TypeError, RuntimeError):
                        pass
                    lbl.original_pixmap = QPixmap()
                    lbl.highlights = []
                    lbl.color_map = {}
                    lbl.setPixmap(QPixmap())
                    lbl._hl_cache = None
                    lbl._hl_cache_key = None
                else:
                    lbl = PDFPageLabel(QPixmap(), [], {})

                lbl.page_index = page_idx
                lbl.setFixedSize(int(w_px), int(h_px))
                # Parent to container but keep hidden; virtual scroll will
                # show + position only the pages near the viewport.
                lbl.setParent(self.source_container)

                self._source_page_slots.append(lbl)
                self._source_page_slot_data.append({"materialized": False})

                full_text += (
                    f"--- Page {page_idx + 1} ---\n" + page.get_text("text") + "\n\n"
                )

            doc.close()
            self.source_text_edit.setText(full_text)

            # Set container height so the scrollbar covers all pages
            if self._source_page_dims:
                total_h = int(
                    self._source_page_y_offsets[-1] + self._source_page_dims[-1][1] + 10
                )
            else:
                total_h = 0
            self.source_container.setMinimumHeight(total_h)

        # Build highlights for all matches from this source
        zoom = self.zoom_level

        current_color = QColor(255, 180, 50, 110)  # gold
        other_color = QColor(250, 170, 30, 40)  # amber-muted

        # Keys identifying which reference rects belong to the actively-clicked match
        current_rect_keys: set = set()
        for ref_page, ref_rect, _ in source_data:
            current_rect_keys.add(
                (ref_page, ref_rect.x0, ref_rect.y0, ref_rect.x1, ref_rect.y1)
            )

        # Scan the COMPLETE results to collect every match from this source file.
        # This ensures all reference locations are visible and navigable, not just
        # the one that was clicked.
        # Also collect target-side data (page, rect, word) for each reference rect,
        # so hovering in the reference viewer can show a preview of the target text.
        #
        # IMPORTANT: Rect collection and is_current determination are separate steps.
        # If done in a single pass, processing order can cause a shared rkey (from
        # overlapping SW-expanded blocks) to be permanently stamped as non-current
        # when a non-current block's target words are iterated before the current one.
        seen_rect_keys: set = set()
        # Map: rkey → fitz.Rect object (the first one seen, for dedup)
        all_rect_objects: dict = {}
        # Map: ref_page → list of rkeys on that page (preserves insertion order)
        rkeys_by_page: dict = {}
        # Map: ref_rect_key → list of (target_page, target_rect, word) triples
        target_data_by_ref_rect: dict = {}
        for target_page_idx, page_highlights in self.current_results.items():
            for h in page_highlights:
                if h.source != file_path or h.ignored:
                    continue
                # Collect the target-side triple for this highlight word
                target_triple = (target_page_idx, h.rect, h.word)
                for ref_page, ref_rect, _ in h.source_data or []:
                    rkey = (
                        ref_page,
                        ref_rect.x0,
                        ref_rect.y0,
                        ref_rect.x1,
                        ref_rect.y1,
                    )
                    # Accumulate target data for each reference rect
                    target_data_by_ref_rect.setdefault(rkey, []).append(target_triple)
                    if rkey in seen_rect_keys:
                        continue
                    seen_rect_keys.add(rkey)
                    all_rect_objects[rkey] = ref_rect
                    rkeys_by_page.setdefault(ref_page, []).append(rkey)

        # Determine is_current purely from current_rect_keys (order-independent)
        all_highlights_by_page: dict = {}
        for ref_page, rkeys in rkeys_by_page.items():
            all_highlights_by_page[ref_page] = [
                (all_rect_objects[rkey], rkey in current_rect_keys) for rkey in rkeys
            ]

        # Fallback when there are no comparison results yet (e.g., browse mode
        # before a comparison has been run).
        if not all_highlights_by_page:
            for ref_page, ref_rect, _ in source_data:
                if ref_page not in all_highlights_by_page:
                    all_highlights_by_page[ref_page] = []
                all_highlights_by_page[ref_page].append((ref_rect, True))

        # Build the reference-navigation index (sorted page list + initial position)
        self._source_match_pages = sorted(all_highlights_by_page.keys())
        if tp is not None and tp in self._source_match_pages:
            self._source_match_page_idx = self._source_match_pages.index(tp)
        else:
            self._source_match_page_idx = 0

        # When opened without a specific match (browse mode), scroll to first
        # highlighted page instead of the top of the document.
        scroll_page = (
            tp
            if tp is not None
            else (self._source_match_pages[0] if self._source_match_pages else None)
        )

        def _merge_rects(rects):
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

        for slot_idx, lbl in enumerate(self._source_page_slots):
            p_idx = lbl.page_index
            page_highlight_data = all_highlights_by_page.get(p_idx, [])

            # IMPORTANT: copy rects before merging! _merge_rects mutates rects in-place
            # (widening x1). The originals come from reference_maps, so mutating them
            # would permanently corrupt the shared index and break future comparisons.
            current_rects = [
                fitz.Rect(r) for r, is_curr in page_highlight_data if is_curr
            ]
            other_rects = [
                fitz.Rect(r) for r, is_curr in page_highlight_data if not is_curr
            ]

            merged_current = _merge_rects(current_rects)
            merged_other = _merge_rects(other_rects)

            highlights = []

            # Build per-rect target preview data by finding which original
            # rects overlap each merged rect (merging unions nearby rects,
            # so we collect target triples from all constituents).
            def _target_data_for_merged(merged_rect, rects_with_data):
                """Collect target triples from original rects that overlap the merged rect."""
                triples = []
                for orig_r, orig_triples in rects_with_data:
                    # Check if the original rect was merged into this merged rect
                    if (
                        orig_r.y0 >= merged_rect.y0 - 1
                        and orig_r.y1 <= merged_rect.y1 + 1
                        and orig_r.x0 >= merged_rect.x0 - 1
                        and orig_r.x1 <= merged_rect.x1 + 1
                    ):
                        triples.extend(orig_triples)
                return triples

            # Pre-compute per-rect target data
            current_rects_with_data = []
            other_rects_with_data = []
            for r, is_curr in page_highlight_data:
                rkey = (p_idx, r.x0, r.y0, r.x1, r.y1)
                triples = target_data_by_ref_rect.get(rkey, [])
                if is_curr:
                    current_rects_with_data.append((r, triples))
                else:
                    other_rects_with_data.append((r, triples))

            for r in merged_other:
                rect_triples = _target_data_for_merged(r, other_rects_with_data)
                highlights.append(
                    HighlightEntry(
                        rect=fitz.Rect(
                            r.x0 * zoom, r.y0 * zoom, r.x1 * zoom, r.y1 * zoom
                        ),
                        source="OTHER_MATCH",
                        preview_source=self.current_target_file,
                        source_data=rect_triples or None,
                        match_id=id(r),
                        confidence=0.3,
                    )
                )
            for r in merged_current:
                rect_triples = _target_data_for_merged(r, current_rects_with_data)
                highlights.append(
                    HighlightEntry(
                        rect=fitz.Rect(
                            r.x0 * zoom, r.y0 * zoom, r.x1 * zoom, r.y1 * zoom
                        ),
                        source="CURRENT_MATCH",
                        preview_source=self.current_target_file,
                        source_data=rect_triples or None,
                        match_id=id(r),
                        confidence=1.0,
                    )
                )

            lbl.color_map = {
                "OTHER_MATCH": other_color,
                "CURRENT_MATCH": current_color,
            }
            lbl.highlights = highlights
            lbl._hl_cache_key = None  # invalidate cached highlight pixmap
            if self._source_page_slot_data[slot_idx]["materialized"]:
                lbl.draw_highlights()

        # Materialize visible source pages (first load or after highlight refresh)
        QTimer.singleShot(0, self._update_visible_source_pages)

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

        # Scroll with delay to ensure container height is applied
        if scroll_page is not None and scroll_page < len(self._source_page_y_offsets):
            scroll_y = int(self._source_page_y_offsets[scroll_page])

            def _scroll_source():
                self.source_scroll.verticalScrollBar().setValue(scroll_y)
                self._update_visible_source_pages()

            QTimer.singleShot(50, _scroll_source)
            hdr_to_find = f"--- Page {scroll_page + 1} ---"
            cursor = doc_obj.find(hdr_to_find)
            if not cursor.isNull():
                QTimer.singleShot(
                    50, lambda: self.source_text_edit.setTextCursor(cursor)
                )
                QTimer.singleShot(
                    50, lambda: self.source_text_edit.ensureCursorVisible()
                )

        # Show/hide ◀▶ navigation buttons based on number of highlighted pages
        self.update_match_controls()

    def keyPressEvent(self, event):
        """Global keyboard shortcuts."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
                self.change_zoom(0.1)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Minus:
                self.change_zoom(-0.1)
                event.accept()
                return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Handle Ctrl+Scroll for zooming."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.change_zoom(0.1)
            elif delta < 0:
                self.change_zoom(-0.1)
            event.accept()
        else:
            super().wheelEvent(event)

    def closeEvent(self, event):
        """Clean up resources on window close."""
        self.target_renderer.cleanup()
        self.source_renderer.cleanup()
        super().closeEvent(event)
