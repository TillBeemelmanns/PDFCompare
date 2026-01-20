# Agent Knowledge Base

## Overview
This project is a **Python + PyQt6** desktop application for forensic plagiarism detection. It is designed to be completely offline and privacy-focused.

## Core Components (Agents)

### 1. `PlagiarismChecker` (`plag_logic.py`)
*   **Role:** The "Brain" of the operation.
*   **Responsibilities:**
    *   **PDF Parsing:** Extracts text and coordinates using `PyMuPDF`.
    *   **De-hyphenation:** Merges split words (e.g., "detec-
ion") while preserving original coordinates for accurate highlighting.
    *   **Indexing:** Creates a hash-based inverted index of 3-grams (seeds) from the Pool documents.
    *   **Matching:** Scans the Suspect document for seeds and clusters them into continuous matching blocks using a gap-tolerant algorithm.
    *   **Filtering:** Removes stopwords to improve robustness against minor edits.

### 2. `MainWindow` (`main.py`)
*   **Role:** The "Interface" and coordinator.
*   **Responsibilities:**
    *   **Drag & Drop:** Handles file input via custom `FileListWidget`.
    *   **Visualization:** Renders PDFs as images and draws colored overlays for matches.
    *   **Navigation:** Manages the synchronized view between Suspect and Source documents.
    *   **Interactivity:** Handles clicks on highlights, enabling "drill-down" analysis (jumping to the source context).
    *   **Filtering:** Allows toggling specific source files on/off via the Legend checkboxes.

## Key Algorithms

*   **Seed-and-Extend:** Matches are found by identifying shared N-grams (seeds) and then extending/clustering them if they appear in a consistent sequence (diagonal match in a dotplot).
*   **Gap Tolerance:** The clustering logic allows for small gaps or insertions in the text, making it resilient to minor edits.
*   **De-hyphenation:** A custom pre-processing step ensures that words split across lines are treated as whole words during matching but highlighted as two separate parts in the UI.

## Future Agents / Extensions
*   **ReportGenerator:** Could generate HTML/PDF reports of the findings.
*   **OCRHandler:** Could integrate Tesseract to handle scanned image-only PDFs.
*   **WebSearcher:** could be added to check against online sources (would break offline promise, so make optional).
