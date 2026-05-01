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
def tolltracker_html(fixtures_path: Path) -> str:
    return (fixtures_path / "tolltracker_map.html").read_text(encoding="utf-8")


@pytest.fixture
def kml_text(fixtures_path: Path) -> str:
    return (fixtures_path / "kml_map.kml").read_text(encoding="utf-8")
