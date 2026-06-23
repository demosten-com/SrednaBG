# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the shared geodesic helpers."""

import pytest

from src.geo import point_to_polyline_m


class TestPointToPolyline:
    # A short segment running due east along lat 42.5000.
    LINE = [[42.5000, 23.8000], [42.5000, 23.8020]]

    def test_point_on_line_is_zero(self):
        assert point_to_polyline_m(42.5000, 23.8010, self.LINE) == pytest.approx(0, abs=0.5)

    def test_perpendicular_offset_north(self):
        # ~70 m north of the line.
        d = point_to_polyline_m(42.50063, 23.8010, self.LINE)
        assert d == pytest.approx(70, abs=5)

    def test_beyond_endpoint_clamps_to_terminus(self):
        # West of the segment start: distance is to the start vertex, not the
        # infinite line.
        d = point_to_polyline_m(42.5000, 23.7990, self.LINE)
        assert d == pytest.approx(82, abs=5)

    def test_degenerate_polyline_is_inf(self):
        assert point_to_polyline_m(42.5, 23.8, [[42.5, 23.8]]) == float("inf")
