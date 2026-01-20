# PDFCompare

A professional, local desktop application for document comparison. **PDFCompare** allows you to compare a target PDF against a collection of reference documents to identify and visualize text overlaps with high precision.

## Key Features

*   **100% Offline & Private:** No data ever leaves your machine.
*   **Dual-Phase Detection:**
    *   **Phase A (Shingling):** Rapidly identifies potential matches using N-gram indexing.
    *   **Phase B (Smith-Waterman):** Refines matches using local alignment for optimal boundary detection and gap handling.
*   **Advanced Visualization:**
    *   Side-by-side synchronized view.
    *   High-resolution document Mini-map (Heatmap).
    *   Interactive highlights (Click to jump to source, cycle overlapping matches).
*   **Robust Processing:**
    *   **Fuzzy Matching:** Optional Levenshtein-based matching.
    *   **De-hyphenation:** Intelligent merging of words split across lines.
    *   **Multi-threaded:** UI stays responsive during heavy computation.
*   **Professional UI:** Dark theme, interactive legend, and live statistics (memory/index size).

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/TillBeemelmanns/PDFCompare.git
    cd pdfcompare
    ```

2.  **Set up a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Run the app:** `python main.py`
2.  **Load References:** Drag & drop PDFs into the **Reference PDFs** list.
3.  **Load Target:** Drag & drop the PDF you want to check into the **Target PDF** area.
4.  **Compare:** Click **Run Comparison**.
5.  **Analyze:** Use the **Legend** to filter sources, click highlights to trace context, or right-click to ignore specific matches.

## Testing

Run the full test suite with:
```bash
python3 -m unittest discover tests
```

## Tech Stack

*   **GUI:** [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
*   **PDF Engine:** [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/)
*   **Alignment:** Custom Smith-Waterman implementation
*   **Fuzzy Logic:** [python-Levenshtein](https://github.com/rapidfuzz/python-Levenshtein)
*   **System Stats:** [psutil](https://github.com/giampaolo/psutil)

## License



MIT License - see [LICENSE](LICENSE) for details.
