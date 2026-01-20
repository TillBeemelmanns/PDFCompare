import unittest
import fitz
import os
import sys

# Ensure the root directory is in path so we can import compare_logic
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from compare_logic import PDFComparator


class TestPDFComparator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create small test PDFs once for the class
        cls.ref1_path = "tests/ref1.pdf"
        cls.ref2_path = "tests/ref2.pdf"
        cls.target_path = "tests/target.pdf"
        cls.empty_path = "tests/empty.pdf"

        # Ref 1: Basic text
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "The quick brown fox jumps over the lazy dog.")
        doc.save(cls.ref1_path)
        doc.close()

        # Ref 2: Different text
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Artificial intelligence is transforming the world.")
        doc.save(cls.ref2_path)
        doc.close()

        # Target: Patchwork of Ref 1 and Ref 2
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(
            (50, 50),
            "I saw that the quick brown fox jumps over the lazy dog. Truly, artificial intelligence is transforming the world today.",
        )
        doc.save(cls.target_path)
        doc.close()

        # Empty
        doc = fitz.open()
        doc.new_page()
        doc.save(cls.empty_path)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        for p in [cls.ref1_path, cls.ref2_path, cls.target_path, cls.empty_path]:
            if os.path.exists(p):
                os.remove(p)

    def setUp(self):
        self.comparator = PDFComparator()

    def test_multi_source_matching(self):
        """Verify that matches from multiple files are detected correctly."""
        self.comparator.add_references([self.ref1_path, self.ref2_path])
        results, total, stats = self.comparator.compare_document(self.target_path)

        self.assertIn(self.ref1_path, stats)
        self.assertIn(self.ref2_path, stats)
        # Ref 1: "quick brown fox jumps lazy dog" (5 meaningful words)
        self.assertGreaterEqual(stats[self.ref1_path], 5)
        # Ref 2: "artificial intelligence transforming world" (4 meaningful words)
        self.assertGreaterEqual(stats[self.ref2_path], 4)

    def test_zero_matches(self):
        """Verify that a completely unique document returns no stats."""
        self.comparator.add_references([self.ref1_path])

        # Create a unique doc
        unique_path = "tests/unique.pdf"
        doc = fitz.open()
        doc.new_page().insert_text(
            (50, 50), "Seven stars shine bright in the midnight sky."
        )
        doc.save(unique_path)
        doc.close()

        try:
            results, total, stats = self.comparator.compare_document(unique_path)
            self.assertEqual(len(stats), 0)
        finally:
            os.remove(unique_path)

    def test_empty_document(self):
        """Verify that empty documents don't cause crashes."""
        self.comparator.add_references([self.empty_path])
        results, total, stats = self.comparator.compare_document(self.target_path)
        self.assertEqual(len(stats), 0)

        results, total, stats = self.comparator.compare_document(self.empty_path)
        self.assertEqual(total, 0)

    def test_seed_size_sensitivity(self):
        """Verify that changing seed size affects detection sensitivity."""
        self.comparator.add_references([self.ref1_path])

        # With seed size 10, the short sentence in target shouldn't match well
        self.comparator.seed_size = 10
        _, _, stats_strict = self.comparator.compare_document(self.target_path)

        # With seed size 3, it should match
        self.comparator.seed_size = 3
        _, _, stats_lenient = self.comparator.compare_document(self.target_path)

        self.assertGreater(
            stats_lenient.get(self.ref1_path, 0), stats_strict.get(self.ref1_path, 0)
        )

    def test_dehyphenation_logic(self):
        """Verify that split words are correctly merged."""
        # We manually call the internal helper with split words
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "hyphen-")
        page.insert_text((50, 70), "ation")

        merged = self.comparator._extract_and_dehyphenate(doc)
        doc.close()

        # Should have found one merged word "hyphenation"
        words = [m[1] for m in merged]
        self.assertIn("hyphenation", words)

    def test_real_pdf_parsing(self):
        """Verify that a real PDF can be indexed and self-compared."""
        sample_path = "pdfs/pdflatex-4-pages.pdf"
        if not os.path.exists(sample_path):
            self.skipTest(f"{sample_path} not found")

        self.comparator.add_references([sample_path])
        stats_initial = self.comparator.get_stats()
        self.assertGreater(stats_initial["total_ngrams"], 0)
        self.assertEqual(stats_initial["reference_files"], 1)

        # Self-comparison
        results, total, stats = self.comparator.compare_document(sample_path)

        # Self-similarity should be extremely high (nearly 100%)
        self.assertIn(sample_path, stats)
        match_count = stats[sample_path]

        # At least 95% of meaningful words should match itself
        # Note: 'total' is total tokens (including stopwords), stats[sample_path] is matching filtered tokens.
        # So we should compare against the number of filtered tokens.
        doc_sample = fitz.open(sample_path)
        filtered_total = len(
            list(
                self.comparator._filter_words_merged(
                    self.comparator._extract_and_dehyphenate(doc_sample)
                )
            )
        )
        doc_sample.close()
        similarity = (match_count / filtered_total) if filtered_total > 0 else 0
        self.assertGreater(similarity, 0.95)


if __name__ == "__main__":
    unittest.main()
