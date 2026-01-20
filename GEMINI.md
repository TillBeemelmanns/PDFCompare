# Forensic Plagiarism Checker

## Project Overview

**PDFCompare** is a local desktop application designed for forensic plagiarism detection. It compares a "Target" PDF document against a "Reference Pool" of PDF files to identify and visualize text overlaps.

**Key Features:**
*   **Offline Privacy:** Runs entirely locally; no data is uploaded to the cloud.
*   **Dual-Phase Detection:**
    *   **Phase A:** Fast N-Gram shingling for initial candidate filtering.
    *   **Phase B:** Smith-Waterman local alignment for precise, gap-tolerant match refinement.
*   **Visual Comparison:**
    *   **Target Viewer:** Displays the suspect document with color-coded highlights.
    *   **Reference Viewer:** Side-by-side view of the source document, automatically scrolled to the matching text.
    *   **Mini-Map:** High-level heatmap of matches for quick navigation.
    *   **Image Tooltips:** Hover over matches to see an instant image preview of the source text.
*   **Interactive Analysis:**
    *   **Drill-Down:** Click on overlapping highlights to cycle through multiple sources.
    *   **Ignore Matches:** Context menu to exclude specific matches from the report.
    *   **Zoom & Navigation:** smooth zooming and keyboard shortcuts (Space, Mouse Side Buttons).
*   **Robustness:**
    *   **De-hyphenation:** Intelligently merges words split across lines in PDFs.
    *   **Fuzzy Matching:** Optional Levenshtein-based matching for detecting rewrites.
*   **Performance:** Multi-threaded processing and optimized memory management.

## Tech Stack
*   **Language:** Python 3
*   **GUI:** PyQt6
*   **PDF Engine:** PyMuPDF (fitz)
*   **Algorithms:** Custom Smith-Waterman & N-Gram implementation.

## Architecture
*   **MVC Pattern:** Separation of Logic (`compare_logic.py`) and UI (`gui/`).
*   **Workers:** Background threads (`gui/workers.py`) prevent UI freezing during heavy processing.
*   **Widgets:** Custom components (`PDFPageLabel`, `PreviewPopup`) handling specialized rendering and interaction.

## Building and Running

### Prerequisites
*   Python 3.x installed on your system.

### Setup
1.  **Create a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Execution
To start the application:
```bash
python main.py
```