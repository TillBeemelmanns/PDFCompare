import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from compare_logic import PDFComparator


class TestSmithWaterman(unittest.TestCase):
    def setUp(self):
        self.comparator = PDFComparator()

    def test_sw_alignment_perfect(self):
        # Target: "A B C D E"
        # Source: "A B C D E"
        # Match: "A B C D E"
        seq1 = ["a", "b", "c", "d", "e"]
        seq2 = ["a", "b", "c", "d", "e"]
        match_idxs = self.comparator._run_smith_waterman(seq1, seq2)
        # Should return indices in seq1 that match: 0, 1, 2, 3, 4
        self.assertEqual(match_idxs, [0, 1, 2, 3, 4])

    def test_sw_alignment_gap(self):
        # Target: "A B X C D E" (Insertion X)
        # Source: "A B C D E"
        # Match: "A B" ... "C D E"
        seq1 = ["a", "b", "x", "c", "d", "e"]
        seq2 = ["a", "b", "c", "d", "e"]
        match_idxs = self.comparator._run_smith_waterman(seq1, seq2)
        # Expected: 0, 1 (A,B) and 3, 4, 5 (C,D,E) -> 2 (X) is skipped
        self.assertEqual(match_idxs, [0, 1, 3, 4, 5])

    def test_sw_alignment_mismatch(self):
        # Target: "A B Y D E" (Substitution Y for C)
        # Source: "A B C D E"
        seq1 = ["a", "b", "y", "d", "e"]
        seq2 = ["a", "b", "c", "d", "e"]
        match_idxs = self.comparator._run_smith_waterman(seq1, seq2)
        # Expected: 0,1, 3,4.
        self.assertEqual(match_idxs, [0, 1, 3, 4])


if __name__ == "__main__":
    unittest.main()
