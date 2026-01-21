# Agent Guidelines & Context

## Project: PDFCompare 

**Goal:** Maintain and enhance a PyQt6-based desktop application for forensic document comparison. The tool focuses on privacy (local execution), precision (Smith-Waterman algorithm), and user experience (visualizations, interactivity).

## Core Components

*   **`main.py`**: Bootstrapper.
*   **`gui/main_window.py`**: Main application controller. Handles layout, user interaction, rendering logic, and state management (zoom, current matches).
*   **`gui/widgets.py`**:
    *   `PDFPageLabel`: Displays PDF pages with overlay highlights. Handles events (hover, click, scroll wheel).
    *   `PreviewPopup`: Floating tooltip showing image snapshots of source matches.
    *   `MiniMapWidget`: Sidebar visualization of document-wide matches.
*   **`gui/workers.py`**: `QThread` workers for `IndexWorker` (hashing) and `CompareWorker` (matching).
*   **`compare_logic.py`**: Core algorithm engine.
    *   Phase A: N-Gram shingling for candidate generation.
    *   Phase B: Smith-Waterman local alignment for refinement.
    *   Utilities: PDF text extraction, de-hyphenation, stopword filtering.

## Design Philosophy

1.  **"If it breaks, it breaks":** Avoid broad `try-except` blocks. Let errors surface to stdout/stderr for debugging unless a specific recovery strategy exists.
2.  **Performance:**
    *   Reuse widgets (`PDFPageLabel`) where possible; avoid constant destruction/creation.
    *   Explicitly release resources (e.g., `QPixmap`) to manage memory (RSS).
    *   Use `QTimer` for delayed actions (e.g., scrolling) to avoid race conditions.
3.  **UX First:**
    *   Instant visual feedback (tooltips, highlights).
    *   Intuitive navigation (Space/Click to cycle, mouse side buttons).
    *   Clear indicators (Loading states, memory stats, shortcuts legend).

## Workflow Mandates

*   **Linting:** After modifying code, ALWAYS run:
    *   `ruff format .`
    *   `ruff check .` (and `ruff check --fix .` if safe)
*   **Testing:** After any logic change, ALWAYS run:
    *   `python -m unittest discover tests`
*   **Safety:** Explain filesystem operations before execution.

