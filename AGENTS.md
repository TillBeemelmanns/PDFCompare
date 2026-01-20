# Agent Knowledge Base

## Overview
This project is a **Python + PyQt6** desktop application for forensic document comparison (PDFCompare). It is designed to be completely offline and privacy-focused.

## Core Components (Agents)

### 1. `PDFComparator` (`compare_logic.py`)
*   **Role:** The "Brain" of the operation.
*   **Responsibilities:**
    *   **PDF Parsing:** Extracts text and coordinates using `PyMuPDF`.
    *   **De-hyphenation:** Merges split words (e.g., "detec-
tion") while preserving original coordinates.
    *   **Phase A (Shingling):** Creates an inverted index of 3-grams from Reference documents and identifies candidate regions in the Target.
    *   **Phase B (Alignment):** Runs Smith-Waterman local alignment on candidate blocks to find optimal match boundaries.
    *   **Filtering:** Normalizes tokens and removes stopwords to improve robustness.

### 2. `MainWindow` (`gui/main_window.py`)
*   **Role:** The "Interface" and coordinator.
*   **Responsibilities:**
    *   **Orchestration:** Manages background workers (`workers.py`) for indexing and comparison.
    *   **Visualization:** Coordinates rendering of the Target, Reference, and Mini-map views.
    *   **Global State:** Tracks ignored match IDs and legend check states to filter the UI.
    *   **Navigation:** Synchronizes the view when a user clicks a match in the Target document.

### 3. Custom Widgets (`gui/widgets.py`)
*   **`PDFPageLabel`:** Interactive canvas that renders PDF pages and overlays highlights. Handles clicks and right-click context menus.
*   **`MiniMapWidget`:** A high-resolution heatmap showing match density across the entire document height.
*   **`FileListWidget`:** Enhanced list with drag-and-drop support for PDF files.

## Key Algorithms

*   **Seed-and-Extend (Phase A):** Rapidly finds potential matches by hashing word shingles (N-grams).
*   **Smith-Waterman (Phase B):** Provides mathematically optimal local alignment for text sequences, ensuring continuous highlights despite minor gaps or edits.
*   **Heatmap Coordinate Mapping:** Maps PDF point coordinates to widget pixels across multiple pages to provide an accurate document-wide overview.

## Future Agents / Extensions
*   **ReportGenerator:** Could generate HTML/PDF reports of the findings.
*   **OCRHandler:** Could integrate Tesseract to handle scanned image-only PDFs.