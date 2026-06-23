# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the OSM Overpass scraper's error handling.

OSM has zero enforcement=average_speed relations for Bulgaria as of 2026-06,
so every code path here is expected to yield 0 zones — the point is that a
flaky public endpoint degrades to an empty list, never an exception.
"""

from unittest.mock import MagicMock

import overpy

from src import osm_overpass


def _api_raising(exc: Exception) -> MagicMock:
    api = MagicMock()
    api.query.side_effect = exc
    return api


class TestQueryErrorHandling:
    def test_unexpected_http_status_returns_empty(self):
        # Overpass intermittently answers 406 when overloaded; must not raise.
        exc = overpy.exception.OverpassUnknownHTTPStatusCode(406)
        assert osm_overpass.query_average_speed_relations(_api_raising(exc)) == []

    def test_rate_limit_returns_empty(self):
        exc = overpy.exception.OverpassTooManyRequests()
        assert osm_overpass.query_average_speed_relations(_api_raising(exc)) == []

    def test_gateway_timeout_returns_empty(self):
        exc = overpy.exception.OverpassGatewayTimeout()
        assert osm_overpass.query_average_speed_relations(_api_raising(exc)) == []

    def test_generic_failure_returns_empty(self):
        assert osm_overpass.query_average_speed_relations(
            _api_raising(RuntimeError("boom"))
        ) == []

    def test_success_returns_relations(self):
        api = MagicMock()
        result = MagicMock()
        result.relations = [MagicMock(), MagicMock()]
        api.query.return_value = result
        assert len(osm_overpass.query_average_speed_relations(api)) == 2
