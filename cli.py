#!/usr/bin/env python3
"""
PDFCompare CLI — analyse a target PDF against a pool of reference PDFs.

Outputs structured JSON describing text overlaps, designed for AI agent
consumption (e.g. LaTeX rewriting workflows).

Usage:
    python cli.py --target doc.pdf --refs ref1.pdf ref2.pdf
    python cli.py --target doc.pdf --refs pool/          # folder of PDFs
    python cli.py --target doc.pdf --refs pool/ --output results.json

Exit codes:
    0  success
    1  error
"""

import argparse
import json
import os
import sys

from compare_logic import PDFComparator


def _collect_pdfs(paths: list[str]) -> list[str]:
    """Expand directories to contained PDF files (recursive)."""
    result = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(".pdf"):
                        result.append(os.path.join(root, f))
        elif p.lower().endswith(".pdf"):
            result.append(p)
        else:
            print(f"Warning: skipping {p!r} — not a PDF or directory", file=sys.stderr)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pdfcompare",
        description=(
            "Analyse a target PDF against reference PDFs and output match data as JSON."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--target", required=True, metavar="PDF", help="Target PDF to analyse"
    )
    parser.add_argument(
        "--refs",
        required=True,
        nargs="+",
        metavar="PDF_OR_DIR",
        help="Reference PDFs or directories (searched recursively for *.pdf)",
    )
    parser.add_argument(
        "--mode",
        choices=["fast", "fuzzy"],
        default="fast",
        help="'fast' = exact n-gram, 'fuzzy' = Levenshtein (tolerates OCR errors)",
    )
    parser.add_argument(
        "--seed-size",
        type=int,
        default=3,
        metavar="N",
        help="Minimum consecutive words required for a candidate match",
    )
    parser.add_argument(
        "--no-sw",
        action="store_true",
        help="Disable Smith-Waterman refinement (faster, less precise boundaries)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        metavar="FLOAT",
        help="Exclude matches below this confidence score (0.0 – 1.0)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write JSON to FILE instead of stdout",
    )
    args = parser.parse_args()

    ref_files = _collect_pdfs(args.refs)
    if not ref_files:
        print("Error: no reference PDF files found.", file=sys.stderr)
        sys.exit(1)

    comparator = PDFComparator()
    comparator.seed_size = args.seed_size

    # --- Index references ---
    print(f"Indexing {len(ref_files)} reference file(s)...", file=sys.stderr)

    def _index_progress(current: int, total: int) -> None:
        print(f"  [{current}/{total}] indexed", file=sys.stderr, end="\r")

    comparator.add_references(ref_files, progress_callback=_index_progress)
    print(file=sys.stderr)  # newline after \r progress line

    # --- Compare ---
    print(f"Comparing against {args.target!r}...", file=sys.stderr)
    highlights, total_words, source_stats = comparator.compare_document(
        args.target,
        mode=args.mode,
        use_sw=not args.no_sw,
    )

    # --- Reconstruct match text from highlights ---
    # Iterate pages in ascending order to preserve document reading order.
    # Each highlight carries the original word string ("word" key) and a
    # match_id that groups all words belonging to the same aligned block.
    match_groups: dict[int, dict] = {}
    for page_idx in sorted(highlights):
        for h in highlights[page_idx]:
            if h.get("ignored"):
                continue
            mid = h["match_id"]
            if mid not in match_groups:
                match_groups[mid] = {
                    "target_words": [],
                    "source_file": h["source"],
                    "source_data": h["source_data"],
                    "confidence": h["confidence"],
                }
            match_groups[mid]["target_words"].append(h["word"])

    # --- Build output matches list ---
    matches = []
    for grp in match_groups.values():
        if grp["confidence"] < args.min_confidence:
            continue
        target_text = " ".join(grp["target_words"])
        source_text = " ".join(w for _, _, w in grp["source_data"])
        matches.append(
            {
                "target_text": target_text,
                "source_file": grp["source_file"],
                "source_text": source_text,
                "confidence": round(grp["confidence"], 3),
                "word_count": len(grp["target_words"]),
            }
        )

    # Highest confidence / longest matches first
    matches.sort(key=lambda m: (m["confidence"], m["word_count"]), reverse=True)

    summary = {
        "target": args.target,
        "references": ref_files,
        "total_words": total_words,
        "total_matches": len(matches),
        "sources": {
            src: {
                "matched_words": cnt,
                "overlap_pct": round(100.0 * cnt / max(1, total_words), 1),
            }
            for src, cnt in source_stats.items()
        },
    }

    result = {"summary": summary, "matches": matches}
    json_str = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"Results written to {args.output!r}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
