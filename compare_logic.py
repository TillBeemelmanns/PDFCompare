import fitz  # PyMuPDF
from collections import defaultdict
import Levenshtein


class PDFComparator:
    def __init__(self):
        self.reference_index = defaultdict(list)
        self.word_index = defaultdict(list)
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
            doc = fitz.open(fp)
            merged = self._extract_and_dehyphenate(doc)
            doc.close()
            filtered = list(self._filter_words_merged(merged))
            self.reference_maps[fp] = [(x[2], x[1]) for x in filtered]
            for idx, norm_word, _ in filtered:
                self.word_index[norm_word].append((fp, idx))
            for idx, gram in self._generate_grams(filtered, self.seed_size):
                self.reference_index[hash(gram)].append((fp, idx))

    def _run_smith_waterman(self, seq1, seq2):
        m, n = len(seq1), len(seq2)
        if m == 0 or n == 0:
            return []
        match_score, mismatch_penalty, gap_penalty = 2, -1, -1
        score_matrix = [[0] * (n + 1) for _ in range(m + 1)]
        max_score, max_pos = 0, (0, 0)
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                diag = score_matrix[i - 1][j - 1] + (
                    match_score if seq1[i - 1] == seq2[j - 1] else mismatch_penalty
                )
                up, left = (
                    score_matrix[i - 1][j] + gap_penalty,
                    score_matrix[i][j - 1] + gap_penalty,
                )
                score = max(0, diag, up, left)
                score_matrix[i][j] = score
                if score > max_score:
                    max_score, max_pos = score, (i, j)
        if max_score == 0:
            return []
        align_indices, i, j = [], max_pos[0], max_pos[1]
        while i > 0 and j > 0 and score_matrix[i][j] > 0:
            score, score_diag = score_matrix[i][j], score_matrix[i - 1][j - 1]
            is_match = seq1[i - 1] == seq2[j - 1]
            if score == score_diag + (
                match_score if is_match else mismatch_penalty
            ) or (is_match and score >= score_diag):
                if is_match:
                    align_indices.append(i - 1)
                i, j = i - 1, j - 1
            elif score == score_matrix[i - 1][j] + gap_penalty:
                i -= 1
            else:
                j -= 1
        return sorted(align_indices)

    def compare_document(self, target_path, mode="fast", use_sw=True, sw_expansion=1):
        doc = fitz.open(target_path)
        merged_target = self._extract_and_dehyphenate(doc)
        doc.close()
        if not merged_target:
            return {}, 0, {}
        filtered_target = list(self._filter_words_merged(merged_target))
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
            for filt_idx, target_gram in self._generate_grams(
                filtered_target, self.seed_size
            ):
                candidates, target_str = defaultdict(int), " ".join(target_gram)
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
                                raw_matches.append(
                                    {
                                        "target_filt_idx": filt_idx,
                                        "src_file": src_fp,
                                        "src_filt_idx": src_idx,
                                    }
                                )
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
                dist, gap_t, gap_s = (
                    m["target_filt_idx"] - curr["end"],
                    m["target_filt_idx"] - (curr["end"] - self.seed_size),
                    m["src_filt_idx"] - curr["last_src_idx"],
                )
                if (
                    m["src_file"] == curr["src"]
                    and dist <= self.merge_distance
                    and dist >= -self.seed_size
                    and abs(gap_t - gap_s) <= 5
                ):
                    curr["end"], curr["last_src_idx"] = (
                        max(curr["end"], m["target_filt_idx"] + self.seed_size),
                        m["src_filt_idx"],
                    )
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
        final_highlights, source_word_counts = defaultdict(list), defaultdict(set)
        for block in merged_blocks:
            if block["end"] - block["start"] < 3:
                continue
            indices, s_start, s_end = (
                range(block["start"], block["end"]),
                block["src_start_idx"],
                block["src_start_idx"] + (block["end"] - block["start"]),
            )
            if use_sw:
                exp = sw_expansion
                t_s, t_e = (
                    max(0, block["start"] - exp),
                    min(len(filtered_target), block["end"] + exp),
                )
                src_len = block["end"] - block["start"]
                s_s_win = max(0, block["src_start_idx"] - exp)
                s_map = self.reference_maps.get(block["src"], [])
                s_e_win = min(len(s_map), block["src_start_idx"] + src_len + exp)
                aligned = self._run_smith_waterman(
                    [filtered_target[i][1] for i in range(t_s, t_e)],
                    [s_map[i][1] for i in range(s_s_win, s_e_win)],
                )
                aligned_g = [t_s + i for i in aligned]
                if len(aligned_g) > (block["end"] - block["start"]) * 0.5:
                    indices, s_start, s_end = aligned_g, s_s_win, s_e_win
            source_info = []
            if block["src"] in self.reference_maps:
                s_map = self.reference_maps[block["src"]]
                s_start, s_end = (
                    max(0, min(s_start, len(s_map))),
                    max(0, min(s_end, len(s_map))),
                )
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
                            }
                        )
                        source_word_counts[block["src"]].add(i)
        return (
            final_highlights,
            len(merged_target),
            {src: len(idxs) for src, idxs in source_word_counts.items()},
        )

    def get_stats(self):
        return {
            "total_ngrams": len(self.reference_index),
            "reference_files": len(self.reference_maps),
        }
