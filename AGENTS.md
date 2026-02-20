# Agent Guidelines & Context

## Project: PDFCompare

**Goal:** Maintain and enhance a PyQt6-based desktop application for forensic document comparison. The tool focuses on privacy (local execution), precision (Smith-Waterman algorithm), and user experience (visualizations, interactivity).

## Core Components

- **`main.py`** — Entry point / bootstrapper.

- **`gui/main_window.py`** — Main application controller. Handles layout, user interaction, state management, and rendering coordination.
  - Virtual scroll for both target and reference viewers: only pages near the viewport are materialized (pixmap set); distant pages are dematerialized to free RAM.
  - Background render pool (`QThreadPool`, 2 threads): `_pending_bg_render_worker` for target, `_pending_bg_source_worker` for reference. Both use `PageRenderWorker` and share `_bg_render_pool`.
  - Widget pool (`self.widget_pool`): plain `list` of recycled `PDFPageLabel` instances, not a separate class.
  - Debounced target refresh (`_refresh_timer`, 150 ms) and throttled scroll handlers (`_virtual_scroll_timer`, `_source_scroll_timer`, 50 ms each).

- **`gui/pdf_renderer.py`** — High-performance PDF rendering engine.
  - `PixmapCache` — Memory-aware LRU cache keyed by `(file_path, page_idx, zoom)`. Evicts LRU pages once estimated RAM exceeds the configured byte budget.
  - `PDFRenderer` — Wraps `PixmapCache`. Key methods: `get_cached_pixmap`, `batch_prerender` (opens fitz once for a batch of pages), `store_pixmap` (inserts a pre-rendered pixmap from a background worker), `get_page_dimensions`.

- **`gui/widgets.py`**
  - `PDFPageLabel` — Displays a PDF page as a `QLabel` with overlay highlights, hover preview, and click/ignore signals. Caches the composited highlight pixmap (`_hl_cache`) keyed by `_hl_cache_key`.
  - `PreviewPopup` — Floating tooltip showing an async-rendered crop of a source match.
  - `FileListWidget` — Drag-and-drop file list with animations and folder support.
  - `MiniMapWidget` — Navigation heatmap for the target document.

- **`gui/workers.py`** — Background workers.
  - `IndexWorker` (`QObject` / `QThread`) — Calls `PDFComparator.add_references`.
  - `CompareWorker` (`QObject` / `QThread`) — Calls `PDFComparator.compare_document`.
  - `PageRenderWorker` (`QRunnable`) — Rasterises a list of page indices into `QImage` objects off-thread; the main thread converts to `QPixmap` on callback. Used for both target and reference async rendering. Supports `cancel()`.
  - `PreviewWorker` (`QRunnable`) — Generates cropped, highlighted preview images for hover tooltips.

- **`compare_logic.py`** — Core algorithm engine.
  - **Phase A:** N-gram shingling (`seed_size` words). Matching is parallelised via `ThreadPoolExecutor`. Supports exact (`fast`) and Levenshtein fuzzy (`fuzzy`) modes.
  - **Phase B:** Smith-Waterman local alignment. NumPy-vectorised implementation.
  - **Incremental index cache:** Reference PDF word data is cached to `~/.pdfcompare/index_cache/` as `{md5}.pkl` files. Cache key = MD5(path + mtime + size). Only the fitz-parsed/filtered word data is stored; n-grams are regenerated each run (Python `hash()` is not stable across processes). `fitz.Rect` objects are serialised as plain `(x0, y0, x1, y1)` tuples for pickle portability.
  - `_INDEX_CACHE_DIR` — `Path` constant exported at module level; imported by `main_window.py` for the "Clear Index Cache" button.
  - `STOPWORDS` — Module-level `frozenset` for memory efficiency.

## Design Philosophy

1. **"If it breaks, it breaks"** — Avoid broad `try-except` blocks. Let errors surface for debugging. The only intentional silent catch is `_save_index_cache`, which is non-critical.
2. **Performance**
   - **Incremental indexing:** Reference PDFs are parsed with fitz at most once per file version; subsequent runs load pre-parsed word data from disk in milliseconds.
   - **Async rendering:** Both viewers dispatch uncached pages to `PageRenderWorker` so the main thread never blocks on fitz rasterisation.
   - **LRU pixmap cache:** 256 MB for target, 128 MB for reference; memory-bounded eviction.
   - **Widget pooling:** `PDFPageLabel` instances are recycled across renders.
   - **Batch prerender:** `batch_prerender` opens fitz once to warm the cache before virtual scroll activates.
   - **Parallelised n-gram matching:** `ThreadPoolExecutor` splits grams across workers.
   - **NumPy:** Vectorised Smith-Waterman.
   - **`QTimer` throttling / debouncing:** Scroll updates capped at ~20 fps; legend/zoom changes coalesced into one render.
3. **UX First**
   - Catppuccin dark theme.
   - Animated drag-and-drop with visual feedback.
   - Cache and memory statistics always visible.
   - Intuitive navigation (Space / click to cycle overlapping matches, mouse side buttons, MiniMap).

## Workflow Mandates

- **Linting:** After modifying code, ALWAYS run:
  - `ruff format .`
  - `ruff check .` (and `ruff check --fix .` if safe)
- **Testing:** After any logic change, ALWAYS run:
  - `python -m unittest discover tests`
- **Safety:** Explain filesystem operations before execution.
