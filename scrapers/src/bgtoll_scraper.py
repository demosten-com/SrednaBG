# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Scrape certified average speed sections from bgtoll.bg.

Parses the FAQ page HTML table to extract road names, start/end settlements,
and km markers. Does NOT provide GPS coordinates (those come from TollTracker).
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from src.fetch import fetch_text
from src.roads import infer_direction_from_km, normalize_road, road_slug
from src.zone_schema import SpeedLimits, Zone, ZoneEndpoint

logger = logging.getLogger(__name__)

BGTOLL_URL = "https://bgtoll.bg/vaprosi-i-otgovori"

# Default speed limits by road type (km/h)
MOTORWAY_SPEED_LIMITS = SpeedLimits(car=140, truck=90, bus=100, motorcycle=140)
NATIONAL_ROAD_SPEED_LIMITS = SpeedLimits(car=90, truck=80, bus=80, motorcycle=90)


@dataclass
class RawSection:
    """Raw parsed row from BG TOLL table."""

    road: str
    start_text: str
    end_text: str


def fetch_page(url: str = BGTOLL_URL, timeout: int = 30) -> str:
    """Fetch the BG TOLL FAQ page HTML."""
    return fetch_text(url, timeout=timeout, label="BG TOLL")


def parse_html(html: str) -> list[RawSection]:
    """Parse the HTML table to extract raw section data."""
    soup = BeautifulSoup(html, "html.parser")
    sections = []

    # Find the table - try multiple strategies
    table = None
    scroll_div = soup.find("div", id="scroll-hint")
    if scroll_div:
        table = scroll_div.find("table")
    if not table:
        # Fallback: find any table containing motorway names
        for t in soup.find_all("table"):
            if t.find(string=re.compile(r"АМ\s")):
                table = t
                break

    if not table:
        logger.warning("No sections table found in BG TOLL HTML")
        return sections

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        road = _normalize_text(cells[0].get_text())
        start_text = _normalize_text(cells[1].get_text())
        end_text = _normalize_text(cells[2].get_text())

        if not road or not start_text or not end_text:
            logger.warning("Skipping row with empty cells: %s", cells)
            continue

        sections.append(RawSection(road=road, start_text=start_text, end_text=end_text))

    logger.info("Parsed %d sections from BG TOLL", len(sections))
    return sections


def _normalize_text(text: str) -> str:
    """Strip and normalize unicode text."""
    text = unicodedata.normalize("NFC", text.strip())
    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def parse_km(km_str: str) -> float:
    """Parse a km marker string like '24+288' into km as float (24.288)."""
    match = re.search(r"(\d+)\+(\d+)", km_str)
    if not match:
        raise ValueError(f"Cannot parse km marker: '{km_str}'")
    km = int(match.group(1))
    meters = int(match.group(2))
    return km + meters / 1000.0


def parse_point_text(text: str) -> tuple[str, str | None]:
    """Parse 'Вакарел (км 24+288)' into ('Вакарел', '24+288').

    Returns (settlement, km_marker) where km_marker may be None.
    """
    match = re.match(r"^(.+?)\s*\(км\s*(\d+\+\d+)\)$", text)
    if match:
        return match.group(1).strip(), match.group(2)

    # Fallback: try without parentheses
    match = re.match(r"^(.+?)\s+км\s*(\d+\+\d+)$", text)
    if match:
        return match.group(1).strip(), match.group(2)

    # No km marker found - return just the text
    return text.strip(), None


def normalize_road_name(raw: str) -> str:
    """Normalize BG TOLL road name to canonical form."""
    return normalize_road(raw)


def infer_direction(road: str, start_km: float, end_km: float) -> str:
    """Infer travel direction from road name and km marker ordering."""
    return infer_direction_from_km(road, start_km, end_km)


def to_zones(sections: list[RawSection]) -> list[Zone]:
    """Convert raw sections to Zone objects with placeholder coordinates."""
    zones = []

    for section in sections:
        try:
            road = normalize_road_name(section.road)
            start_settlement, start_km_str = parse_point_text(section.start_text)
            end_settlement, end_km_str = parse_point_text(section.end_text)

            if start_km_str is None or end_km_str is None:
                logger.warning(
                    "Skipping section without km markers: %s -> %s",
                    section.start_text,
                    section.end_text,
                )
                continue

            start_km = parse_km(start_km_str)
            end_km = parse_km(end_km_str)
            distance_m = int(abs(end_km - start_km) * 1000)

            if distance_m <= 0:
                logger.warning("Zero distance for section: %s", section)
                continue

            direction = infer_direction(road, start_km, end_km)
            slug = road_slug(road)

            # Use motorway or national road speed limits
            is_motorway = road.startswith("АМ")
            speed_limits = (
                MOTORWAY_SPEED_LIMITS if is_motorway else NATIONAL_ROAD_SPEED_LIMITS
            )

            description = f"{start_settlement} – {end_settlement}"

            zone = Zone(
                id=f"{slug}-{start_km_str}-{direction}",  # Temporary ID
                road=road,
                direction=direction,
                description=description,
                start=ZoneEndpoint(
                    lat=0.0,
                    lng=0.0,
                    km_marker=start_km_str,
                    settlement=start_settlement,
                ),
                end=ZoneEndpoint(
                    lat=0.0,
                    lng=0.0,
                    km_marker=end_km_str,
                    settlement=end_settlement,
                ),
                distance_m=distance_m,
                speed_limits=speed_limits,
                centerline=[],
                source="bgtoll",
                last_verified=datetime.now(UTC).strftime("%Y-%m-%d"),
            )
            zones.append(zone)
        except Exception:
            logger.warning(
                "Failed to parse section: %s", section, exc_info=True
            )
            continue

    logger.info("Converted %d BG TOLL sections to zones", len(zones))
    return zones


def scrape(html: str | None = None) -> list[Zone]:
    """Main entry point. Fetch and parse BG TOLL data.

    Args:
        html: Pre-fetched HTML (for testing). If None, fetches from network.
    """
    try:
        if html is None:
            html = fetch_page()
        sections = parse_html(html)
        return to_zones(sections)
    except Exception:
        logger.warning("BG TOLL scraper failed", exc_info=True)
        return []
