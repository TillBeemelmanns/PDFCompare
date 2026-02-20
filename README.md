# PDFCompare

A local-first, forensic PDF comparison tool built with PyQt6.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## Features

- **Privacy First** — All processing happens locally. No data ever leaves your machine.
- **Two-Phase Algorithm**
  - *Phase A:* Parallelised N-gram shingling for fast candidate detection.
  - *Phase B:* Smith-Waterman local alignment (NumPy-optimised) for precise match boundaries and a confidence score.
  - Optional fuzzy (Levenshtein) matching for OCR errors and minor typos.
- **Incremental Indexing** — Reference PDFs are parsed once and cached to `~/.pdfcompare/index_cache/`. Subsequent runs with unchanged files skip fitz entirely; Phase A completes in under a second.
- **Async Rendering** — Both the target and reference viewers render uncached pages in background threads, keeping the UI fully responsive while scrolling large documents.
- **Virtual Scroll** — Only pages near the viewport hold a rendered pixmap; distant pages are dematerialised to keep RAM usage bounded.
- **LRU Pixmap Cache** — 256 MB budget for the target viewer, 128 MB for the reference viewer; least-recently-used pages are evicted automatically.
- **Rich Visualisation**
  - Colour-coded highlights per source file.
  - Floating preview tooltip on hover (rendered asynchronously).
  - MiniMap navigation heatmap on the target document.
  - Text view with inline word highlighting as an alternative to the PDF view.
- **Interactive Navigation** — Click a highlight to jump to its source; Space / mouse side-buttons cycle through overlapping matches.
- **Modern UI** — Catppuccin-inspired dark theme throughout.

## Installation

1. Clone the repository.
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
## Usage

1. Run the application:
   ```bash
   python main.py
   ```
2. Drag and drop one or more **Reference PDFs** into the *Reference PDFs* panel.
3. Drag and drop the **Target PDF** into the *Target PDF* slot.
4. Adjust algorithm parameters if needed:
   | Parameter | Description |
   |-----------|-------------|
   | Seed Size | Minimum consecutive words required for a candidate match (higher = fewer, more reliable matches). |
   | Merge Gap | Maximum word gap between adjacent matches to merge into one block. |
   | Compare Mode | *Fast* (exact n-gram) or *Fuzzy* (Levenshtein, tolerates OCR errors). |
   | Smith-Waterman | Refines boundaries and adds a confidence score; disable for a faster but coarser result. |
   | Context Lookahead | Extra words inspected beyond each n-gram boundary during Smith-Waterman. |
5. Click **Run Comparison**.
6. Explore the results:
   - **Hover** a highlight to see a floating source preview.
   - **Click** a highlight to jump to the full context in the Reference Viewer.
   - **Space** or **click again** on the same area to cycle through overlapping matches.
   - Use the **◀ ▶** buttons or the MiniMap to navigate between matches.
   - Toggle the **legend checkboxes** to show/hide individual sources.
   - Switch to **Text View** for a plain-text diff view of the reference document.

### Cache management

- The index cache lives at `~/.pdfcompare/index_cache/`.
- It is invalidated automatically when a reference file changes (mtime or size).
- Click **🗑 Clear Index Cache** in the left panel to force a full re-parse on the next run.
- Click **✕ Clear Results** to reset both viewers without clearing the file lists.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl +` / `Ctrl -` | Zoom in / out |
| `Ctrl + Scroll` | Zoom in / out |
| `Space` | Next match (when hovering a highlight) |
| Mouse Back / Forward | Previous / next match |

## Project Structure

```
pdfcompare/
├── main.py               # Entry point
├── compare_logic.py      # Phase A & B algorithms, incremental index cache
├── gui/
│   ├── main_window.py    # Main window, layout, state management
│   ├── pdf_renderer.py   # LRU pixmap cache, batch prerender, store_pixmap
│   ├── widgets.py        # PDFPageLabel, PreviewPopup, FileListWidget, MiniMapWidget
│   └── workers.py        # IndexWorker, CompareWorker, PageRenderWorker, PreviewWorker
├── tests/                # Unit tests
└── requirements.txt
```

## License

MIT
