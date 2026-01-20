# Forensic Plagiarism Checker

## Project Overview

This is a local desktop application designed for forensic plagiarism detection. It compares a "Suspect" PDF document against a "Pool" of reference PDF files to identify and visualize text overlaps.

**Key Features:**
*   **Offline Privacy:** Runs entirely locally; no data is uploaded to the cloud.
*   **Visual Comparison:** Side-by-side view of the suspect document and the matched source document.
*   **Forensic Highlighting:** Interactive highlights trace plagiarized sections back to their original context.
*   **Fuzzy Matching:** Optional Levenshtein-based matching to detect rewrites and minor edits.
*   **De-hyphenation:** Intelligently merges words split across lines in PDFs to ensure accurate matching.
*   **Scoring:** Calculates and displays a similarity percentage for each source file.
*   **Filtering:** Interactively toggle specific source files to isolate matches.
*   **Dark Mode:** Built-in dark theme for comfortable viewing.
*   **Statistics:** Displays memory usage and index size.

**Tech Stack:**
*   **Language:** Python 3
*   **GUI:** PyQt6
*   **PDF Engine:** PyMuPDF (fitz)
*   **Utilities:** psutil (system stats)

## Architecture

*   **`main.py`**: The entry point and GUI implementation. Handles the Main Window, Drag-and-Drop file lists, PDF Rendering (visual and text modes), interaction logic, and visualization.
*   **`plag_logic.py`**: Contains the `PlagiarismChecker` class. Implements the core logic:
    *   **Preprocessing:** Token normalization, stopword removal, and de-hyphenation.
    *   **Indexing:** Builds an inverted index of 3-grams from the pool.
    *   **Detection:** Finds matches in the suspect document and clusters them into continuous blocks using a gap-tolerant merge strategy.

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

1.  **Load Pool:** Drag and drop one or more reference PDF files into the "Pool PDFs" list on the left.
2.  **Load Suspect:** Drag and drop the PDF you want to investigate into the "Suspect PDF" list.
3.  **Configure:** Adjust "Seed Size" (sensitivity) and "Merge Gap" (tolerance) if needed.
4.  **Run:** Click "Run Comparison".
5.  **Analyze:**
    *   Review the similarity scores in the Legend. Uncheck items to filter the view.
    *   Scroll through the Suspect Document (right panel) to see highlighted matches.
    *   **Click** on a highlighted section to instantly open the corresponding Source Document (middle panel), scrolled to the matching text.
    *   Use the `<` and `>` buttons in the middle panel header to cycle through overlapping matches.
    *   Toggle "Switch to Text View" in the middle panel to inspect raw text if the PDF layout is complex.
    *   Check the "Statistics" box at the bottom left for index size and memory usage.

## Development Conventions

*   **Code Style:** The project uses `ruff` for code formatting.
    ```bash
    # Install ruff
    pip install ruff

    # Format code
    ruff format .
    ```
*   **Testing:** Manual testing with sample PDFs is currently the primary verification method.