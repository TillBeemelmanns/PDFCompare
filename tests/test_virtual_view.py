import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.virtual_view import VirtualPdfView


class _FakeContainer:
    """Records the geometry calls VirtualPdfView.resize_container makes."""

    def __init__(self):
        self.min_size = None
        self.size = None

    def setMinimumSize(self, w, h):
        self.min_size = (w, h)

    def resize(self, w, h):
        self.size = (w, h)


class _FakeWindow:
    def __init__(self):
        self.zoom_level = 1.0
        self.widget_pool = []
        self._MAX_POOL_SIZE = 50
        self._bg_render_pool = None


def _make_view(container=None):
    """Build a view with fakes; scroll/renderer are unused by geometry tests."""
    return VirtualPdfView(
        window=_FakeWindow(),
        renderer=None,
        scroll=None,
        container=container or _FakeContainer(),
    )


class TestPageGeometry(unittest.TestCase):
    def test_build_y_offsets_accumulates_height_plus_gap(self):
        view = _make_view()
        # PAGE_GAP is 10; heights are 100, 200, 50.
        offsets = view._build_y_offsets([(400, 100), (400, 200), (400, 50)])
        self.assertEqual(offsets, [0, 110, 320])

    def test_set_page_geometry_sizes_container_to_cover_all_pages(self):
        container = _FakeContainer()
        view = _make_view(container)
        view.set_page_geometry([(400, 100), (612, 200), (300, 50)])

        # offsets: [0, 110, 320]; total = last_offset + last_height + gap.
        expected_total_h = 320 + 50 + view.PAGE_GAP
        expected_max_w = 612
        self.assertEqual(view.offsets, [0, 110, 320])
        self.assertEqual(container.min_size, (expected_max_w, expected_total_h))
        self.assertEqual(container.size, (expected_max_w, expected_total_h))

    def test_empty_geometry_yields_zero_sized_container(self):
        container = _FakeContainer()
        view = _make_view(container)
        view.set_page_geometry([])
        self.assertEqual(view.offsets, [])
        self.assertEqual(container.min_size, (0, 0))


class TestScrollAnchorRoundTrip(unittest.TestCase):
    def setUp(self):
        self.view = _make_view()
        self.view.set_page_geometry([(400, 100), (400, 200), (400, 50)])

    def test_anchor_round_trip_is_identity_within_bounds(self):
        # Each value lands inside a page (or its trailing gap), so capture →
        # restore must reproduce the exact scrollbar value.
        for value in (0, 50, 100, 110, 250, 310, 320, 330):
            anchor = self.view.capture_scroll_anchor(scroll_value=value)
            self.assertIsNotNone(anchor)
            restored = self.view.scroll_value_from_anchor(anchor)
            self.assertEqual(restored, value, f"round-trip failed for {value}")

    def test_capture_returns_page_relative_offset(self):
        # value 250 sits 140 px into page 1 (which starts at offset 110).
        self.assertEqual(self.view.capture_scroll_anchor(scroll_value=250), (1, 140))

    def test_capture_without_geometry_returns_none(self):
        empty = _make_view()
        self.assertIsNone(empty.capture_scroll_anchor(scroll_value=100))

    def test_scroll_value_from_none_anchor_is_zero(self):
        self.assertEqual(self.view.scroll_value_from_anchor(None), 0)


class TestZonePartition(unittest.TestCase):
    def test_partition_splits_pages_by_overlap_with_zone(self):
        view = _make_view()
        view.set_page_geometry([(400, 100), (400, 200), (400, 50)])
        # Page extents: p0 [0,100], p1 [110,310], p2 [320,370].
        in_zone, out_zone = view.partition_pages_by_zone(150, 330)
        self.assertEqual(in_zone, [1, 2])
        self.assertEqual(out_zone, [0])


class TestRenderEpoch(unittest.TestCase):
    def test_bump_increments_and_returns(self):
        view = _make_view()
        self.assertEqual(view.render_epoch, 0)
        self.assertEqual(view.bump_render_epoch(), 1)
        self.assertEqual(view.bump_render_epoch(), 2)
        self.assertEqual(view.render_epoch, 2)

    def test_is_current_render_requires_matching_file_and_epoch(self):
        view = _make_view()
        view.file = "/tmp/a.pdf"
        view.bump_render_epoch()  # epoch -> 1
        self.assertTrue(view.is_current_render("/tmp/a.pdf", 1))
        self.assertFalse(view.is_current_render("/tmp/a.pdf", 0))  # stale epoch
        self.assertFalse(view.is_current_render("/tmp/b.pdf", 1))  # stale file


if __name__ == "__main__":
    unittest.main()
