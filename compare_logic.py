import fitz  # PyMuPDF
from collections import defaultdict
import Levenshtein


class PDFComparator:
    def __init__(self):
        # Index: trigram_hash -> list of (source_filename, filtered_word_index)
        self.reference_index = defaultdict(list)
        # Word index for fuzzy candidate generation: word -> list of (source_filename, filtered_word_index)
        self.word_index = defaultdict(list)
        # Map: filename -> list of (parts_list, normalized_word) corresponding to filtered_words indices
        self.reference_maps = {}

        self.seed_size = 3
        self.merge_distance = 15
        self.STOPWORDS = {
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
            "they've",
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

    def _normalize(self, text):
        return "".join(c for c in text if c.isalnum()).lower()

    def _extract_and_dehyphenate(self, doc):
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

    def _filter_words_merged(self, merged_words):
        for i, (parts, text) in enumerate(merged_words):
            norm = self._normalize(text)
            if not norm or not norm.isalnum():
                continue
            if norm not in self.STOPWORDS:
                yield i, norm, parts

    def _generate_grams(self, filtered_words, n):
        if len(filtered_words) < n:
            return
        word_strs = [x[1] for x in filtered_words]
        for i in range(len(filtered_words) - n + 1):
            gram = tuple(word_strs[i : i + n])
            yield i, gram

    def add_references(self, file_paths):
        self.reference_index.clear()
        self.word_index.clear()
        self.reference_maps.clear()

        for fp in file_paths:
            try:
                doc = fitz.open(fp)
                merged = self._extract_and_dehyphenate(doc)
                doc.close()
                filtered = list(self._filter_words_merged(merged))

                # reference_maps stores [(parts, norm_word), ...]
                self.reference_maps[fp] = [(x[2], x[1]) for x in filtered]

                for idx, norm_word, _ in filtered:
                    self.word_index[norm_word].append((fp, idx))

                for idx, gram in self._generate_grams(filtered, self.seed_size):
                    self.reference_index[hash(gram)].append((fp, idx))
            except Exception as e:
                print(f"Error reading reference file {fp}: {e}")

    def _run_smith_waterman(self, seq1, seq2):
        """
        Runs Smith-Waterman local alignment on two word sequences.
        Returns a list of indices in seq1 that are part of the alignment.
        """
        m, n = len(seq1), len(seq2)
        if m == 0 or n == 0:
            return []

        # Scoring
        match_score = 2
        mismatch_penalty = -1
        gap_penalty = -1

        # Initialize matrix
        # rows: 0..m (seq1), cols: 0..n (seq2)
        score_matrix = [[0] * (n + 1) for _ in range(m + 1)]

        max_score = 0
        max_pos = (0, 0)

        # Fill matrix
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                score_diag = score_matrix[i - 1][j - 1] + (
                    match_score if seq1[i - 1] == seq2[j - 1] else mismatch_penalty
                )
                score_up = score_matrix[i - 1][j] + gap_penalty
                score_left = score_matrix[i][j - 1] + gap_penalty

                score = max(0, score_diag, score_up, score_left)
                score_matrix[i][j] = score

                if score > max_score:
                    max_score = score
                    max_pos = (i, j)

        if max_score == 0:
            return []

        # Traceback
        align_indices = []
        i, j = max_pos

        while i > 0 and j > 0 and score_matrix[i][j] > 0:
            score = score_matrix[i][j]
            score_diag = score_matrix[i - 1][j - 1]
            score_up = score_matrix[i - 1][j]
            score_left = score_matrix[i][j - 1]

            # Check diagonal (Match/Mismatch)
            is_match = seq1[i - 1] == seq2[j - 1]
            expected_diag_score = score_diag + (
                match_score if is_match else mismatch_penalty
            )

            # Prefer diagonal moves if scores match (greedy match)
            if score == expected_diag_score or (is_match and score >= score_diag):
                if is_match:
                    align_indices.append(i - 1)  # 0-based index
                i -= 1
                j -= 1
            elif score == score_up + gap_penalty:
                i -= 1  # Deletion in seq2 (gap in alignment against seq1), skip seq1 word
            elif score == score_left + gap_penalty:
                j -= 1  # Insertion in seq2, stay on seq1 word
            else:
                # Should not happen, but fallback to diagonal
                i -= 1
                j -= 1

        return sorted(align_indices)

    def compare_document(self, target_path, mode="fast", use_sw=True, sw_expansion=1):
        try:
            doc = fitz.open(target_path)
        except:
            return {}, 0, {}

        merged_target = self._extract_and_dehyphenate(doc)
        doc.close()
        if not merged_target:
            return {}, 0, {}

        filtered_target = list(self._filter_words_merged(merged_target))
        total_words_count = len(merged_target)
        raw_matches = []

        if mode == "fast":
            for filt_idx, gram in self._generate_grams(filtered_target, self.seed_size):
                h = hash(gram)
                if h in self.reference_index:
                    for src_fp, src_idx in self.reference_index[h]:
                        raw_matches.append(
                            {
                                "target_filt_idx": filt_idx,
                                "src_file": src_fp,
                                "src_filt_idx": src_idx,
                            }
                        )
        else:
            # Fuzzy Mode using Levenshtein distance on shingles
            MAX_WORD_DIST = 1
            for filt_idx, target_gram in self._generate_grams(
                filtered_target, self.seed_size
            ):
                candidates = defaultdict(int)
                for word in target_gram:
                    for src_fp, src_word_idx in self.word_index.get(word, []):
                        for offset in range(self.seed_size):
                            shingle_start = src_word_idx - offset
                            if shingle_start >= 0:
                                candidates[(src_fp, shingle_start)] += 1

                target_str = " ".join(target_gram)
                for (src_fp, src_idx), shared_count in candidates.items():
                    if shared_count >= (self.seed_size - 1):
                        s_map = self.reference_maps.get(src_fp, [])
                        if src_idx + self.seed_size <= len(s_map):
                            # Reconstruct source shingle text
                            src_shingle_words = [
                                s_map[i][1]
                                for i in range(src_idx, src_idx + self.seed_size)
                            ]
                            src_str = " ".join(src_shingle_words)

                            # Word-level edit distance check
                            if Levenshtein.distance(target_str, src_str) <= 5:
                                raw_matches.append(
                                    {
                                        "target_filt_idx": filt_idx,
                                        "src_file": src_fp,
                                        "src_filt_idx": src_idx,
                                    }
                                )

        # Clustering Logic
        raw_matches.sort(key=lambda x: (x["src_file"], x["target_filt_idx"]))
        merged_blocks = []
        if raw_matches:
            current_block = None
            for m in raw_matches:
                if current_block is None:
                    current_block = {
                        "src": m["src_file"],
                        "start": m["target_filt_idx"],
                        "end": m["target_filt_idx"] + self.seed_size,
                        "last_src_idx": m["src_filt_idx"],
                        "src_start_idx": m["src_filt_idx"],
                    }
                    continue
                dist_target = m["target_filt_idx"] - current_block["end"]
                gap_target = m["target_filt_idx"] - (
                    current_block["end"] - self.seed_size
                )
                gap_src = m["src_filt_idx"] - current_block["last_src_idx"]
                if (
                    m["src_file"] == current_block["src"]
                    and dist_target <= self.merge_distance
                    and dist_target >= -self.seed_size
                    and abs(gap_target - gap_src) <= 5
                ):
                    current_block["end"] = max(
                        current_block["end"], m["target_filt_idx"] + self.seed_size
                    )
                    current_block["last_src_idx"] = m["src_filt_idx"]
                else:
                    merged_blocks.append(current_block)
                    current_block = {
                        "src": m["src_file"],
                        "start": m["target_filt_idx"],
                        "end": m["target_filt_idx"] + self.seed_size,
                        "last_src_idx": m["src_filt_idx"],
                        "src_start_idx": m["src_filt_idx"],
                    }
            if current_block:
                merged_blocks.append(current_block)

        final_highlights = defaultdict(list)
        source_word_counts = defaultdict(set)

        for block in merged_blocks:
            if block["end"] - block["start"] < 3:
                continue

            # Phase B: Smith-Waterman Refinement
            final_indices = range(block["start"], block["end"])
            src_start_idx = block["src_start_idx"]
            src_end_idx = block["src_start_idx"] + (block["end"] - block["start"])

            if use_sw:
                expansion = sw_expansion
                tgt_start_idx = max(0, block["start"] - expansion)
                tgt_end_idx = min(len(filtered_target), block["end"] + expansion)
                target_window_words = [
                    filtered_target[i][1] for i in range(tgt_start_idx, tgt_end_idx)
                ]

                src_len = block["end"] - block["start"]
                src_start_win = max(0, block["src_start_idx"] - expansion)
                s_map = self.reference_maps.get(block["src"], [])
                src_end_win = min(
                    len(s_map), block["src_start_idx"] + src_len + expansion
                )
                source_window_words = [
                    s_map[i][1] for i in range(src_start_win, src_end_win)
                ]

                aligned_indices_relative = self._run_smith_waterman(
                    target_window_words, source_window_words
                )
                aligned_indices_global = [
                    tgt_start_idx + i for i in aligned_indices_relative
                ]

                if len(aligned_indices_global) > (block["end"] - block["start"]) * 0.5:
                    final_indices = aligned_indices_global
                    src_start_idx = src_start_win
                    src_end_idx = src_end_win

            source_info = []
            if block["src"] in self.reference_maps:
                s_map = self.reference_maps[block["src"]]
                src_start_idx = max(0, min(src_start_idx, len(s_map)))
                src_end_idx = max(0, min(src_end_idx, len(s_map)))
                for parts, _ in s_map[src_start_idx:src_end_idx]:
                    for p, r, w in parts:
                        source_info.append((p, r, w))

            match_id = id(block)
            for i in final_indices:
                if i < len(filtered_target):
                    for p, r, w in filtered_target[i][2]:
                        final_highlights[p].append(
                            {
                                "rect": r,
                                "source": block["src"],
                                "source_data": source_info,
                                "match_id": match_id,
                            }
                        )
                        source_word_counts[block["src"]].add(i)

        stats = {src: len(indices) for src, indices in source_word_counts.items()}
        return final_highlights, total_words_count, stats

    def get_stats(self):
        return {
            "total_ngrams": len(self.reference_index),
            "reference_files": len(self.reference_maps),
        }
