# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Orchestrate the scraper pipeline and generate zones.json.

Usage:
    python -m src.output [--output PATH | --target-dir DIR]
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src import bgtoll_scraper, kml_scraper, osm_overpass, tolltracker_fetcher
from src.validator import merge_all, normalize_road
from src.zone_schema import ZoneDatabase

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path(__file__).parent.parent / "data" / "zones.json"
SNAPSHOT_RETENTION = 26
MIN_APP_VERSION = "1.0.0"


def run_pipeline() -> ZoneDatabase:
    """Run all scrapers and merge into a ZoneDatabase."""
    logger.info("Starting zone data pipeline")

    bgtoll_zones = bgtoll_scraper.scrape()
    logger.info("BG TOLL: %d zones", len(bgtoll_zones))

    tolltracker_zones = tolltracker_fetcher.scrape()
    logger.info("TollTracker: %d zones", len(tolltracker_zones))

    kml_zones = kml_scraper.scrape()
    logger.info("KML: %d zones", len(kml_zones))

    osm_zones = osm_overpass.scrape()
    logger.info("OSM Overpass: %d zones", len(osm_zones))

    merged = merge_all(bgtoll_zones, tolltracker_zones, osm_zones, kml_zones)
    logger.info("Merged: %d zones", len(merged))

    db = ZoneDatabase(
        version=ZoneDatabase.now_version(),
        zones=merged,
    )
    return db.with_hash()


def atomic_write_text(path: Path, text: str) -> None:
    """Write text to ``path`` via a same-dir tmp file + os.replace.

    Same-directory tmp ensures os.replace is a true atomic rename on POSIX,
    so concurrent readers always see either the old or the new file.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_output(db: ZoneDatabase, path: Path = DEFAULT_OUTPUT) -> None:
    """Write the zone database to a single JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    json_str = db.model_dump_json(indent=2, exclude_none=True)
    atomic_write_text(path, json_str)
    logger.info("Wrote %d zones to %s", len(db.zones), path)


def _read_prev_hash(version_path: Path) -> str:
    if not version_path.exists():
        return ""
    try:
        return json.loads(version_path.read_text(encoding="utf-8")).get("hash", "")
    except (OSError, ValueError):
        return ""


def write_target_dir(db: ZoneDatabase, dir_: Path) -> str:
    """Write zones.json + version.json into ``dir_`` for live serving.

    Snapshots the prior ``zones.json`` to ``zones-<UTC-timestamp>.json`` only
    when content actually changes. Retains the newest ``SNAPSHOT_RETENTION``
    snapshots and prunes the rest. Returns the previous hash (empty if none).
    """
    dir_.mkdir(parents=True, exist_ok=True)
    zones_path = dir_ / "zones.json"
    version_path = dir_ / "version.json"

    prev_hash = _read_prev_hash(version_path)
    new_text = db.model_dump_json(indent=2, exclude_none=True)

    if zones_path.exists() and zones_path.read_text(encoding="utf-8") != new_text:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(zones_path, dir_ / f"zones-{ts}.json")

    atomic_write_text(zones_path, new_text)

    version_meta = {
        "version": db.version,
        "hash": db.hash,
        "min_app_version": MIN_APP_VERSION,
        "zone_count": len(db.zones),
        "map_hash": None,
    }
    atomic_write_text(version_path, json.dumps(version_meta, indent=2) + "\n")

    snapshots = sorted(dir_.glob("zones-*.json"), reverse=True)
    for old in snapshots[SNAPSHOT_RETENTION:]:
        old.unlink()

    logger.info(
        "Wrote %d zones to %s (prev_hash=%s)",
        len(db.zones), zones_path, prev_hash or "(none)",
    )
    return prev_hash


def print_summary(db: ZoneDatabase) -> None:
    """Print a summary of the generated data."""
    roads: dict[str, int] = {}
    for z in db.zones:
        road = normalize_road(z.road)
        roads[road] = roads.get(road, 0) + 1

    print("\nZone Database Summary")
    print(f"  Version: {db.version}")
    print(f"  Hash: {db.hash}")
    print(f"  Total zones: {len(db.zones)}")
    print("\n  Coverage by road:")
    for road, count in sorted(roads.items()):
        print(f"    {road}: {count} zones")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate zones.json")
    out_group = parser.add_mutually_exclusive_group()
    out_group.add_argument(
        "--output",
        type=Path,
        help=f"Single-file output path (default: {DEFAULT_OUTPUT})",
    )
    out_group.add_argument(
        "--target-dir",
        type=Path,
        help="Production output dir; writes zones.json + version.json atomically "
             "and rotates timestamped snapshots of zones.json on change.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    start = time.monotonic()
    db = run_pipeline()
    if args.target_dir is not None:
        prev_hash = write_target_dir(db, args.target_dir)
    else:
        write_output(db, args.output or DEFAULT_OUTPUT)
        prev_hash = ""
    duration_s = int(time.monotonic() - start)

    print_summary(db)

    # Machine-readable result line for the cron wrapper.
    print(
        f"RESULT zone_count={len(db.zones)} hash={db.hash} "
        f"prev_hash={prev_hash or '-'} duration_s={duration_s}",
        file=sys.stdout,
    )


if __name__ == "__main__":
    main()
