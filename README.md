# PDFCompare

A local-first PDF comparison tool.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## Features

*   **Privacy First:** All processing happens locally on your machine.
*   **Visual Forensics:** Side-by-side comparison with precise highlighting.
*   **Advanced Algorithms:** Uses Smith-Waterman alignment to detect rewrites and partial matches.
*   **Smart Navigation:** Mini-map, tooltips, and click-to-trace functionality.
*   **Performance:** Optimized for speed and memory efficiency with large documents.

## Installation

1.  Clone the repository.
2.  Set up a virtual environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  Run `python main.py`.
2.  Drag and drop your **Reference PDFs** into the left panel.
3.  Drag and drop your **Target PDF** into the target slot.
4.  Adjust settings (Seed Size, Compare Mode) if needed.
5.  Click **Run Comparison**.
6.  Interact with the results:
    *   **Hover** to see source previews.
    *   **Click** to jump to the full context in the Reference Viewer.
    *   **Space** or **Click Again** to cycle through overlapping matches.

## License

MIT
