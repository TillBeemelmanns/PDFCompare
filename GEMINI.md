# PDFCompare

## Project Overview

This is a local desktop application designed for forensic document comparison. It compares a "Target" PDF document against a set of "Reference" PDF files to identify and visualize text overlaps.

**Key Features:**
*   **Offline Privacy:** Runs entirely locally; no data is uploaded to the cloud.
*   **Visual Comparison:** Side-by-side view of the target document and the matched reference document.
*   **Synchronized Highlighting:** Interactive highlights trace overlapping sections back to their original context.
*   **Fuzzy Matching:** Optional Levenshtein-based matching to detect rewrites and minor edits.
*   **Precision Alignment:** Smith-Waterman local alignment (Phase B) to find exact match boundaries.
*   **De-hyphenation:** Intelligently merges words split across lines in PDFs to ensure accurate matching.
*   **Mini-map Heatmap:** High-resolution vertical visualization of all matches across the document.
*   **Multi-threaded:** Background processing for indexing and comparison to keep the UI responsive.
*   **Scoring:** Calculates and displays a similarity percentage for each reference file.
*   **Filtering:** Interactively toggle specific reference files or ignore specific match blocks.
*   **Dark Mode:** Built-in dark theme for comfortable viewing.
*   **Statistics:** Displays memory usage and index size.

**Tech Stack:**
*   **Language:** Python 3
*   **GUI:** PyQt6
*   **PDF Engine:** PyMuPDF (fitz)
*   **Utilities:** psutil (system stats), python-Levenshtein (fuzzy matching)

## Architecture

*   **`main.py`**: The entry point.
*   **`gui/`**: Contains the GUI implementation.
    *   **`main_window.py`**: Handles the Main Window and high-level orchestration.
    *   **`widgets.py`**: Custom widgets like PDF viewers, Mini-map, and Drag-and-Drop lists.
    *   **`workers.py`**: Background threads for heavy computation.
*   **`compare_logic.py`**: Contains the `PDFComparator` class. Implements the core logic:
    *   **Preprocessing:** Token normalization, stopword removal, and de-hyphenation.
    *   **Indexing:** Builds an inverted index of 3-grams from the reference set.
    *   **Detection (Phase A):** Finds candidate matches using N-gram shingling.
    *   **Alignment (Phase B):** Refines matches using Smith-Waterman local alignment.

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

## Usage

1.  **Load References:** Drag and drop one or more reference PDF files into the "Reference PDFs" list on the left.
2.  **Load Target:** Drag and drop the PDF you want to investigate into the "Target PDF" list.
3.  **Configure:** Adjust Phase A (Seed Size, Merge Gap) and Phase B (SW Refinement, Context Lookahead) settings if needed.
4.  **Run:** Click "Run Comparison".
5.  **Analyze:**
    *   Review the similarity scores in the Legend. Uncheck items to filter the view.
    *   Scroll through the Target Document (right panel) to see highlighted matches or use the Mini-map to jump to sections.
    *   **Click** on a highlighted section to instantly open the corresponding Reference Document (middle panel), scrolled to the matching text.
    *   **Right-click** a match to "Ignore this match" globally.
    *   Use the `<` and `>` buttons in the middle panel header to cycle through overlapping matches.
    *   Toggle "Switch to Text View" in the middle panel to inspect raw text.

## Development Conventions

*   **Code Style:** The project uses `ruff` for code formatting.
    ```bash
    # Install ruff
    pip install ruff

    # Format code
    ruff format .
    ```
*   **Testing:** Automated tests are located in the `tests/` directory. Run all tests with:
    ```bash
    python3 -m unittest discover tests
    ```
    Or run a specific test file:
    ```bash
    ./.venv/bin/python3 tests/test_logic.py
    ```
