# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Shared test fixtures for scraper tests."""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_path() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def bgtoll_html(fixtures_path: Path) -> str:
    return (fixtures_path / "bgtoll_sections.html").read_text(encoding="utf-8")


@pytest.fixture
def kml_text(fixtures_path: Path) -> str:
    return (fixtures_path / "kml_map.kml").read_text(encoding="utf-8")


@pytest.fixture
def tolltracker_zones() -> list:
    """Deterministic TollTracker zones matching the BG TOLL fixture zones.

    Built through the real ``parse_feature`` from synthetic tile-feature
    properties, so pipeline-level tests exercise the merge with zones shaped
    exactly like production ones (per-direction, car-only limit, synthesized
    Latin names).
    """
    from src.geo import polyline_length_m
    from src.tolltracker_fetcher import parse_feature

    segments = [
        ("S-PL-VAK1", "Вакарел - Ихтиман, Тракия", 140,
         [[42.550, 23.703], [42.427, 23.855]]),
        ("S-PL-SAN1", "Сандански - Дамяница, Струма", 140,
         [[41.573, 23.240], [41.515, 23.272]]),
        ("S-PL-ILI1", "Илиянци - Чепинци, Европа", 120,
         [[42.765, 23.297], [42.720, 23.400]]),
        ("S-PL-GOR1", "Горни Богров - Чурек, Хемус", 140,
         [[42.725, 23.528], [42.779, 23.736]]),
    ]
    zones = []
    for fid, title, speed, line in segments:
        for suffix, t, cl in [
            ("", title, line),
            ("R", _reversed_title(title), list(reversed(line))),
        ]:
            props = {
                "id": fid + suffix,
                "title": t,
                "type": "section_control",
                "country": "BG",
                "length": round(polyline_length_m(cl)),
                "speed_limit": speed,
                "start_road_oneway": True,
                "start_road_class": "motorway",
            }
            zones.append(parse_feature(props, cl))
    return zones


def _reversed_title(title: str) -> str:
    names, _, road = title.rpartition(", ")
    a, b = names.split(" - ")
    return f"{b} - {a}, {road}"
