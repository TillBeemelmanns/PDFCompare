"""
Shared data models for PDFCompare.

Provides typed structures that replace ad-hoc dicts, ensuring consistent
field presence across all creation and consumption sites.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitz


@dataclass
class HighlightEntry:
    """A single highlighted region in a PDF viewer.

    Used for both:
    - **Result entries** from ``compare_document()`` (stored in ``current_results``).
    - **Display highlights** on ``PDFPageLabel`` widgets (zoom-scaled rects).

    All fields have safe defaults so that construction sites are forced to supply
    only the fields they have, while consumers can always access any attribute
    without ``.get()`` fallbacks.
    """

    rect: fitz.Rect
    """Display rectangle (zoom-scaled for viewers, raw for result entries)."""

    source: str = ""
    """Source file path (result/target viewer) or sentinel
    (``"CURRENT_MATCH"`` / ``"OTHER_MATCH"`` in reference viewer)."""

    confidence: float = 0.7
    """Alignment confidence score (0.0–1.0)."""

    source_data: list | None = None
    """``(page, fitz.Rect, word)`` triples pointing to the
    preview document (reference doc for target viewer, target doc for
    reference viewer)."""

    match_id: int | None = None
    """Unique identifier linking all words of the same match block."""

    match_density: float = 0.0
    """Fraction of the target span actually matched (0.0–1.0)."""

    word: str = ""
    """The target-side word text (used by phrase-ignore logic)."""

    ignored: bool = False
    """Whether this highlight has been excluded by the user."""

    preview_source: str | None = None
    """Override file path for hover previews. When set, the ``PreviewWorker``
    opens this file instead of ``source``. Used by reference-viewer highlights
    to point previews at the target document."""
