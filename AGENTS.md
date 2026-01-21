# Agent Guidelines & Context

## Project: PDFCompare

**Goal:** Maintain and enhance a PyQt6-based desktop application for forensic document comparison. The tool focuses on privacy (local execution), precision (Smith-Waterman algorithm), and user experience (visualizations, interactivity).

## Core Components

*   **`main.py`**: Bootstrapper.
*   **`gui/main_window.py`**: Main application controller with modern Catppuccin-inspired theme. Handles layout, user interaction, and state management.
*   **`gui/pdf_renderer.py`**: High-performance PDF rendering engine.
    *   `PixmapCache`: LRU cache for rendered page pixmaps (default 100 pages).
    *   `WidgetPool`: Reusable PDFPageLabel pool to reduce creation overhead.
    *   `PDFRenderer`: Coordinates caching and pooling for efficient rendering.
*   **`gui/widgets.py`**:
    *   `PDFPageLabel`: PDF pages with overlay highlights, hover/click events.
    *   `PreviewPopup`: Floating tooltip for source match previews.
    *   `FileListWidget`: Enhanced drag-and-drop with animations and folder support.
    *   `MiniMapWidget`: Document navigation heatmap with modern styling.
*   **`gui/workers.py`**: `QThread` workers for `IndexWorker` and `CompareWorker`.
*   **`compare_logic.py`**: Core algorithm engine (parallelized & optimized).
    *   Phase A: N-Gram shingling (parallelized via ThreadPoolExecutor).
    *   Phase B: Smith-Waterman local alignment (NumPy-optimized, with optional Parasail SIMD).
    *   `STOPWORDS`: Class-level frozenset for memory efficiency.
    *   Utilities: PDF text extraction, de-hyphenation.

## Design Philosophy

1.  **"If it breaks, it breaks":** Avoid broad `try-except` blocks. Let errors surface for debugging.
2.  **Performance:**
    *   **Caching:** LRU pixmap cache prevents redundant PDF rendering.
    *   **Widget Pooling:** Reuse `PDFPageLabel` widgets instead of recreate.
    *   **Parallelization:** N-gram matching across multiple threads.
    *   **NumPy/Parasail:** Vectorized Smith-Waterman for ~10x speedup.
    *   Use `QTimer` for delayed UI actions to avoid race conditions.
3.  **UX First:**
    *   Modern dark theme (Catppuccin color palette).
    *   Animated drag-and-drop with visual feedback.
    *   Cache statistics in the UI for transparency.
    *   Intuitive navigation (Space/Click to cycle, mouse side buttons).

## Workflow Mandates

*   **Linting:** After modifying code, ALWAYS run:
    *   `ruff format .`
    *   `ruff check .` (and `ruff check --fix .` if safe)
*   **Testing:** After any logic change, ALWAYS run:
    *   `python -m unittest discover tests`
*   **Safety:** Explain filesystem operations before execution.

