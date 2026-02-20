"""
PDF Comparison Logic Engine.

This module provides the core comparison algorithms:
- Phase A: N-Gram shingling for initial candidate filtering (parallelized)
- Phase B: Smith-Waterman local alignment for precise match refinement (NumPy-optimized)
"""

import fitz  # PyMuPDF
import hashlib
import os
import pickle
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Callable
import numpy as np

import Levenshtein


# Class-level constant for memory efficiency
STOPWORDS = frozenset(
    {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "aren't",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can't",
        "cannot",
        "could",
        "couldn't",
        "did",
        "didn't",
        "do",
        "does",
        "doesn't",
        "doing",
        "don't",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "hadn't",
        "has",
        "hasn't",
        "have",
        "haven't",
        "having",
        "he",
        "he'd",
        "he'll",
        "he's",
        "her",
        "here",
        "here's",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "how's",
        "i",
        "i'd",
        "i'll",
        "i'm",
        "i've",
        "if",
        "in",
        "into",
        "is",
        "isn't",
        "it",
        "it's",
        "its",
        "itself",
        "let's",
        "me",
        "more",
        "most",
        "mustn't",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "ought",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "shan't",
        "she",
        "she'd",
        "she'll",
        "she's",
        "should",
        "shouldn't",
        "so",
        "some",
        "such",
        "than",
        "that",
        "that's",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "there's",
        "these",
        "they",
        "they'd",
        "they'll",
        "they're",
        "they_ve",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "wasn't",
        "we",
        "we'd",
        "we'll",
        "we're",
        "we've",
        "were",
        "weren't",
        "what",
        "what's",
        "when",
        "when's",
        "where",
        "where's",
        "which",
        "while",
        "who",
        "who's",
        "whom",
        "why",
        "why's",
        "with",
        "won't",
        "would",
        "wouldn't",
        "you",
        "you'd",
        "you'll",
        "you're",
        "you_ve",
        "your",
        "yours",
        "yourself",
        "yourselves",
    }
)


_INDEX_CACHE_DIR = Path.home() / ".pdfcompare" / "index_cache"


class PDFComparator:
    """
    High-performance PDF document comparator.

    Uses a two-phase approach:
    1. N-Gram shingling for fast candidate detection (parallelized)
    2. Smith-Waterman alignment for precise match refinement (NumPy-optimized)
    """

    def __init__(self, max_workers: int = 4):
        self.reference_index = defaultdict(list)
        self.word_index = defaultdict(list)
        self.reference_maps = {}
        self.seed_size = 3
        self.merge_distance = 15
        self.max_workers = max_workers

        # Pre-compute hash function for performance
        self._hash = hash

    @staticmethod
    def _cache_key(file_path: str) -> str:
        stat = os.stat(file_path)
        raw = f"{file_path}\x00{stat.st_mtime}\x00{stat.st_size}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _load_index_cache(file_path: str) -> list | None:
        key = PDFComparator._cache_key(file_path)
        cache_path = _INDEX_CACHE_DIR / f"{key}.pkl"
        if cache_path.exists():
            try:
                with cache_path.open("rb") as f:
                    return pickle.load(f)
            except Exception:
                cache_path.unlink(missing_ok=True)
        return None

    @staticmethod
    def _save_index_cache(file_path: str, filtered_raw: list) -> None:
        _INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = PDFComparator._cache_key(file_path)
        try:
            with (_INDEX_CACHE_DIR / f"{key}.pkl").open("wb") as f:
                pickle.dump(filtered_raw, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            pass  # non-critical

    def _normalize(self, text: str) -> str:
        """Normalize text to lowercase alphanumeric characters."""
        return "".join(c for c in text if c.isalnum()).lower()

    def _extract_and_dehyphenate(self, doc) -> list:
        """
        Extract words from PDF with hyphenation handling.

        Merges words split across lines (e.g., "hyphen-" + "ation" -> "hyphenation").
        """
        full_words_meta = []
        for p_idx, page in enumerate(doc):
            text_words = page.get_text("words")
            for w in text_words:
                full_words_meta.append((p_idx, fitz.Rect(w[0], w[1], w[2], w[3]), w[4]))

        merged = []
        i = 0
        while i < len(full_words_meta):
            curr = full_words_meta[i]
            if curr[2].endswith("-") and i + 1 < len(full_words_meta):
                next_w = full_words_meta[i + 1]
                new_text = curr[2][:-1] + next_w[2]
                parts = [(curr[0], curr[1], curr[2]), (next_w[0], next_w[1], next_w[2])]
                merged.append((parts, new_text))
                i += 2
            else:
                parts = [(curr[0], curr[1], curr[2])]
                merged.append((parts, curr[2]))
                i += 1
        return merged

    def _filter_words_merged(self, merged_words: list):
        """Filter out stopwords and non-alphanumeric tokens."""
        for i, (parts, text) in enumerate(merged_words):
            norm = self._normalize(text)
            if not norm or not norm.isalnum():
                continue
            if norm not in STOPWORDS:
                yield i, norm, parts

    def _generate_grams(self, filtered_words: list, n: int):
        """Generate n-grams from filtered words."""
        if len(filtered_words) < n:
            return
        word_strs = [x[1] for x in filtered_words]
        for i in range(len(filtered_words) - n + 1):
            gram = tuple(word_strs[i : i + n])
            yield i, gram

    def _process_reference_file(self, file_path: str) -> tuple:
        """
        Process a single reference file (for parallel execution).

        Returns:
            Tuple of (file_path, ref_map, gram_index_entries, word_index_entries)
        """
        filtered_raw = self._load_index_cache(file_path)

        if filtered_raw is None:
            # Slow path: parse PDF with fitz
            doc = fitz.open(file_path)
            merged = self._extract_and_dehyphenate(doc)
            doc.close()
            filtered = list(self._filter_words_merged(merged))
            # Serialize fitz.Rect → tuple for pickle portability
            filtered_raw = [
                (i, norm, [(p, (r.x0, r.y0, r.x1, r.y1), w) for p, r, w in parts])
                for i, norm, parts in filtered
            ]
            self._save_index_cache(file_path, filtered_raw)

        # Reconstruct with fitz.Rect objects (fast, no I/O)
        filtered = [
            (
                i,
                norm,
                [
                    (p, fitz.Rect(rx0, ry0, rx1, ry1), w)
                    for p, (rx0, ry0, rx1, ry1), w in parts_raw
                ],
            )
            for i, norm, parts_raw in filtered_raw
        ]

        ref_map = [(parts, norm) for (_, norm, parts) in filtered]
        gram_entries = [
            (self._hash(gram), file_path, idx)
            for idx, gram in self._generate_grams(filtered, self.seed_size)
        ]
        word_entries = [(norm_word, file_path, idx) for idx, norm_word, _ in filtered]
        return file_path, ref_map, gram_entries, word_entries

    def add_references(
        self,
        file_paths: list,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """
        Index reference documents for comparison (parallelized).

        Args:
            file_paths: List of PDF file paths
            progress_callback: Optional callback(current, total) for progress updates
        """
        self.reference_index.clear()
        self.word_index.clear()
        self.reference_maps.clear()

        total = len(file_paths)
        completed = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_reference_file, fp): fp
                for fp in file_paths
            }

            for future in as_completed(futures):
                fp, ref_map, gram_entries, word_entries = future.result()

                # Merge into main indices
                self.reference_maps[fp] = ref_map

                for gram_hash, src_fp, idx in gram_entries:
                    self.reference_index[gram_hash].append((src_fp, idx))

                for word, src_fp, idx in word_entries:
                    self.word_index[word].append((src_fp, idx))

                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

    def _run_smith_waterman(self, seq1: list, seq2: list) -> tuple[list, float]:
        """
        NumPy-optimized Smith-Waterman local alignment.

        Returns:
            Tuple of (aligned_indices, confidence_score)
            - aligned_indices: List of indices in seq1 that align with seq2
            - confidence_score: Float 0.0-1.0 indicating alignment quality
        """
        m, n = len(seq1), len(seq2)
        if m == 0 or n == 0:
            return [], 0.0

        # Scoring parameters
        match_score = 2
        mismatch_penalty = -1
        gap_penalty = -1

        # Initialize score matrix with NumPy
        score_matrix = np.zeros((m + 1, n + 1), dtype=np.int32)

        # Build scoring matrix
        max_score = 0
        max_pos = (0, 0)

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                match = match_score if seq1[i - 1] == seq2[j - 1] else mismatch_penalty
                diag = score_matrix[i - 1, j - 1] + match
                up = score_matrix[i - 1, j] + gap_penalty
                left = score_matrix[i, j - 1] + gap_penalty

                score = max(0, diag, up, left)
                score_matrix[i, j] = score

                if score > max_score:
                    max_score = score
                    max_pos = (i, j)

        if max_score == 0:
            return [], 0.0

        # Traceback
        align_indices = []
        i, j = max_pos
        match_count = 0
        total_aligned = 0

        while i > 0 and j > 0 and score_matrix[i, j] > 0:
            score = score_matrix[i, j]
            score_diag = score_matrix[i - 1, j - 1]
            is_match = seq1[i - 1] == seq2[j - 1]
            match = match_score if is_match else mismatch_penalty

            if score == score_diag + match or (is_match and score >= score_diag):
                total_aligned += 1
                if is_match:
                    align_indices.append(i - 1)
                    match_count += 1
                i, j = i - 1, j - 1
            elif score == score_matrix[i - 1, j] + gap_penalty:
                i -= 1
            else:
                j -= 1

        # Calculate confidence score based on:
        # 1. Match ratio within alignment (identity)
        # 2. Coverage of the shorter sequence
        # 3. Alignment score relative to perfect alignment

        identity = match_count / max(1, total_aligned)

        min_len = min(m, n)
        coverage = len(align_indices) / max(1, min_len)

        # Perfect score would be min_len * match_score
        perfect_score = min_len * match_score
        normalized_score = max_score / max(1, perfect_score)

        # Weighted combination: identity most important, then coverage, then raw score
        confidence = (
            (identity * 0.5) + (coverage * 0.3) + (min(1.0, normalized_score) * 0.2)
        )

        return sorted(align_indices), min(1.0, confidence)

    def _match_gram_chunk(self, gram_chunk: list, mode: str) -> list:
        """
        Match a chunk of n-grams against the reference index (for parallel execution).
        """
        matches = []

        if mode == "fast":
            for filt_idx, gram in gram_chunk:
                h = self._hash(gram)
                if h in self.reference_index:
                    for src_fp, src_idx in self.reference_index[h]:
                        matches.append(
                            {
                                "target_filt_idx": filt_idx,
                                "src_file": src_fp,
                                "src_filt_idx": src_idx,
                            }
                        )
        else:  # fuzzy mode
            for filt_idx, target_gram in gram_chunk:
                candidates = defaultdict(int)
                target_str = " ".join(target_gram)

                for word in target_gram:
                    for src_fp, src_word_idx in self.word_index.get(word, []):
                        for offset in range(self.seed_size):
                            start = src_word_idx - offset
                            if start >= 0:
                                candidates[(src_fp, start)] += 1

                for (src_fp, src_idx), count in candidates.items():
                    if count >= (self.seed_size - 1):
                        s_map = self.reference_maps.get(src_fp, [])
                        if src_idx + self.seed_size <= len(s_map):
                            src_str = " ".join(
                                [
                                    s_map[i][1]
                                    for i in range(src_idx, src_idx + self.seed_size)
                                ]
                            )
                            if Levenshtein.distance(target_str, src_str) <= 5:
                                matches.append(
                                    {
                                        "target_filt_idx": filt_idx,
                                        "src_file": src_fp,
                                        "src_filt_idx": src_idx,
                                    }
                                )

        return matches

    def compare_document(
        self,
        target_path: str,
        mode: str = "fast",
        use_sw: bool = True,
        sw_expansion: int = 1,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> tuple:
        """
        Compare target document against indexed references.

        Args:
            target_path: Path to target PDF
            mode: "fast" for exact n-gram matching, "fuzzy" for Levenshtein-based
            use_sw: Whether to use Smith-Waterman refinement
            sw_expansion: Context expansion for Smith-Waterman
            progress_callback: Optional callback(percent, message) for progress

        Returns:
            Tuple of (highlights_dict, total_words, source_stats_dict)
        """
        if progress_callback:
            progress_callback(0, "Extracting text...")

        doc = fitz.open(target_path)
        merged_target = self._extract_and_dehyphenate(doc)
        doc.close()

        if not merged_target:
            return {}, 0, {}

        filtered_target = list(self._filter_words_merged(merged_target))

        if progress_callback:
            progress_callback(10, "Matching n-grams...")

        # Generate all grams
        all_grams = list(self._generate_grams(filtered_target, self.seed_size))

        # Parallelize gram matching
        raw_matches = []
        chunk_size = max(100, len(all_grams) // self.max_workers)
        chunks = [
            all_grams[i : i + chunk_size] for i in range(0, len(all_grams), chunk_size)
        ]

        if len(chunks) > 1 and mode == "fast":
            # Parallel matching for large documents
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [
                    executor.submit(self._match_gram_chunk, chunk, mode)
                    for chunk in chunks
                ]
                for future in as_completed(futures):
                    raw_matches.extend(future.result())
        else:
            # Sequential for small documents or fuzzy mode
            for chunk in chunks:
                raw_matches.extend(self._match_gram_chunk(chunk, mode))

        if progress_callback:
            progress_callback(40, "Merging match blocks...")

        # Sort and merge matches
        raw_matches.sort(key=lambda x: (x["src_file"], x["target_filt_idx"]))

        merged_blocks = []
        if raw_matches:
            curr = None
            for m in raw_matches:
                if curr is None:
                    curr = {
                        "src": m["src_file"],
                        "start": m["target_filt_idx"],
                        "end": m["target_filt_idx"] + self.seed_size,
                        "last_src_idx": m["src_filt_idx"],
                        "src_start_idx": m["src_filt_idx"],
                    }
                    continue

                dist = m["target_filt_idx"] - curr["end"]
                gap_t = m["target_filt_idx"] - (curr["end"] - self.seed_size)
                gap_s = m["src_filt_idx"] - curr["last_src_idx"]

                if (
                    m["src_file"] == curr["src"]
                    and dist <= self.merge_distance
                    and dist >= -self.seed_size
                    and abs(gap_t - gap_s) <= 5
                ):
                    curr["end"] = max(
                        curr["end"], m["target_filt_idx"] + self.seed_size
                    )
                    curr["last_src_idx"] = m["src_filt_idx"]
                else:
                    merged_blocks.append(curr)
                    curr = {
                        "src": m["src_file"],
                        "start": m["target_filt_idx"],
                        "end": m["target_filt_idx"] + self.seed_size,
                        "last_src_idx": m["src_filt_idx"],
                        "src_start_idx": m["src_filt_idx"],
                    }
            if curr:
                merged_blocks.append(curr)

        if progress_callback:
            progress_callback(60, "Refining matches...")

        # Process blocks and apply Smith-Waterman if enabled
        final_highlights = defaultdict(list)
        source_word_counts = defaultdict(set)

        total_blocks = len(merged_blocks)
        for block_idx, block in enumerate(merged_blocks):
            if block["end"] - block["start"] < 3:
                continue

            indices = range(block["start"], block["end"])
            s_start = block["src_start_idx"]
            s_end = block["src_start_idx"] + (block["end"] - block["start"])
            confidence = 0.7  # Default confidence for non-SW matches

            if use_sw:
                exp = sw_expansion
                t_s = max(0, block["start"] - exp)
                t_e = min(len(filtered_target), block["end"] + exp)
                src_len = block["end"] - block["start"]
                s_s_win = max(0, block["src_start_idx"] - exp)
                s_map = self.reference_maps.get(block["src"], [])
                s_e_win = min(len(s_map), block["src_start_idx"] + src_len + exp)

                aligned, sw_confidence = self._run_smith_waterman(
                    [filtered_target[i][1] for i in range(t_s, t_e)],
                    [s_map[i][1] for i in range(s_s_win, s_e_win)],
                )
                aligned_g = [t_s + i for i in aligned]

                if len(aligned_g) > (block["end"] - block["start"]) * 0.5:
                    indices = aligned_g
                    s_start, s_end = s_s_win, s_e_win
                    confidence = sw_confidence
            else:
                # For non-SW matches, calculate confidence based on n-gram coverage
                block_len = block["end"] - block["start"]
                confidence = min(1.0, 0.5 + (block_len / 20.0) * 0.5)

            # Build source info
            source_info = []
            if block["src"] in self.reference_maps:
                s_map = self.reference_maps[block["src"]]
                s_start = max(0, min(s_start, len(s_map)))
                s_end = max(0, min(s_end, len(s_map)))
                for parts, _ in s_map[s_start:s_end]:
                    for p, r, w in parts:
                        source_info.append((p, r, w))

            match_id = id(block)

            for i in indices:
                if i < len(filtered_target):
                    for p, r, w in filtered_target[i][2]:
                        final_highlights[p].append(
                            {
                                "rect": r,
                                "source": block["src"],
                                "source_data": source_info,
                                "match_id": match_id,
                                "confidence": confidence,
                            }
                        )
                        source_word_counts[block["src"]].add(i)

            if progress_callback and total_blocks > 0:
                percent = 60 + int((block_idx / total_blocks) * 35)
                progress_callback(
                    percent, f"Processing block {block_idx + 1}/{total_blocks}"
                )

        if progress_callback:
            progress_callback(100, "Complete")

        return (
            final_highlights,
            len(merged_target),
            {src: len(idxs) for src, idxs in source_word_counts.items()},
        )

    def get_stats(self) -> dict:
        """Return index statistics."""
        return {
            "total_ngrams": len(self.reference_index),
            "reference_files": len(self.reference_maps),
        }
