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
from datetime import UTC, datetime
from pathlib import Path

from src._preflight import require

require("bs4", "requests", "overpy", "pydantic", module="src.output")

from src import (  # noqa: E402
    bgtoll_scraper,
    kml_scraper,
    # osm_overpass,  # disabled for now — see run_pipeline()
    tolltracker_fetcher,
)
from src.client_contract import ContractError, contract_violations  # noqa: E402
from src.feeds import (  # noqa: E402
    DEFAULT_FEED,
    FeedError,
    is_unsupported,
    project,
    served_feeds,
    snapshot_glob,
    snapshot_name,
    version_filename,
    zones_filename,
)
from src.validator import (  # noqa: E402
    REQUIRED_MOTORWAYS,
    align_centerline_to_endpoints,
    merge_all,
    normalize_road,
)
from src.zone_schema import ZoneDatabase  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path(__file__).parent.parent / "data" / "zones.json"
SNAPSHOT_RETENTION = 26
MIN_APP_VERSION = "1.0.0"

# Publish guard: refuse to overwrite good data with a collapsed scrape.
# First line of defense is SourceFailure — any source that raises or comes
# back empty aborts the run before merging. These floors remain as a second
# net against *partial* collapse (a source silently losing most of its
# zones), which per-source failure detection can't see.
MIN_PUBLISH_ZONES = 50
MIN_PREV_RATIO = 0.7


class SourceFailure(RuntimeError):
    """One or more upstream sources failed — the run must not publish.

    Publishing with a missing source would silently degrade the shipped data
    (lost coordinates, Latin names, limits), so a failed source is fatal.
    """

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _scrape_source(name: str, scrape_fn, errors: list[str]) -> list:
    """Run one source scraper, recording a concise error line on failure.

    An empty result counts as failure too: every active source always has
    zones for Bulgaria, so zero means the source broke quietly.
    """
    try:
        zones = scrape_fn()
    except Exception as e:
        logger.error("%s source failed", name, exc_info=True)
        errors.append(f"{name}: {type(e).__name__}: {e}")
        return []
    if not zones:
        errors.append(f"{name}: returned no zones")
        return []
    logger.info("%s: %d zones", name, len(zones))
    return zones


def run_pipeline() -> ZoneDatabase:
    """Run all scrapers and merge into a ZoneDatabase.

    Raises SourceFailure — after attempting every source, so the report
    covers all of them — when any source fails or returns no zones.
    """
    logger.info("Starting zone data pipeline")

    source_errors: list[str] = []
    bgtoll_zones = _scrape_source("BG TOLL", bgtoll_scraper.scrape, source_errors)
    tolltracker_zones = _scrape_source(
        "TollTracker", tolltracker_fetcher.scrape, source_errors
    )
    kml_zones = _scrape_source("KML", kml_scraper.scrape, source_errors)

    # OSM Overpass disabled for now: the API answers 406 and OSM has no
    # enforcement=average_speed relations for Bulgaria anyway, so the call
    # only adds latency and a warning to every run. Re-enable by restoring
    # the _scrape_source call when OSM coverage appears (note: empty-is-
    # failure would need an exemption while OSM legitimately has no BG data).
    # osm_zones = _scrape_source("OSM Overpass", osm_overpass.scrape, source_errors)
    osm_zones: list = []

    if source_errors:
        raise SourceFailure(source_errors)

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
    """Write the zone database to ``path``, plus a sibling per extra feed.

    ``path`` names the feed-1 file (the caller's choice of name is honoured);
    any further served feed is written beside it under its canonical
    ``zones.N.json``. Local runs and the committed snapshot therefore carry the
    same set of files the host serves, which is what lets each app bundle the
    feed it was built for.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    for entry in served_feeds():
        feed = entry["version"]
        target = path if feed == DEFAULT_FEED else path.parent / zones_filename(feed)
        projected = project(db, feed)
        atomic_write_text(target, projected.model_dump_json(indent=2, exclude_none=True))
        logger.info("Wrote %d zones to %s (feed=%d)", len(projected.zones), target, feed)


def _read_version_meta(version_path: Path) -> dict:
    if not version_path.exists():
        return {}
    try:
        meta = json.loads(version_path.read_text(encoding="utf-8"))
        return meta if isinstance(meta, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_prev_hash(version_path: Path) -> str:
    return _read_version_meta(version_path).get("hash", "")


def publish_guard_errors(
    db: ZoneDatabase,
    prev_count: int | None = None,
    feed: int = DEFAULT_FEED,
) -> list[str]:
    """Reasons ``db`` must NOT be published on ``feed``, or [] if it may be.

    ``prev_count`` is the zone count currently being served on that feed (from
    its version.json), when known.
    """
    errors: list[str] = []
    count = len(db.zones)
    if count < MIN_PUBLISH_ZONES:
        errors.append(
            f"only {count} zones scraped (minimum {MIN_PUBLISH_ZONES}) — "
            f"an upstream source has likely broken"
        )
    roads = {normalize_road(z.road) for z in db.zones}
    for motorway in sorted(REQUIRED_MOTORWAYS - roads):
        errors.append(f"no zones for {motorway}")
    if prev_count and count < prev_count * MIN_PREV_RATIO:
        errors.append(
            f"zone count dropped {prev_count} -> {count} "
            f"(more than {int((1 - MIN_PREV_RATIO) * 100)}%)"
        )
    errors.extend(client_contract_errors(db, feed))
    return errors


def all_feeds_guard_errors(
    db: ZoneDatabase, prev_counts: dict[int, int | None] | None = None
) -> list[str]:
    """Guard every served feed, labelled by feed.

    Deliberately all-or-nothing at the call site: if any feed refuses, nothing
    is written for any feed. A half-updated `/api` — feed 1 fresh, feed 2 stale
    — is worse than a uniformly stale one, because nothing downstream can tell
    the two apart.
    """
    prev_counts = prev_counts or {}
    errors: list[str] = []
    for entry in served_feeds():
        feed = entry["version"]
        projected = project(db, feed)
        label = "" if feed == DEFAULT_FEED else f"feed {feed}: "
        errors.extend(
            f"{label}{err}"
            for err in publish_guard_errors(projected, prev_counts.get(feed), feed)
        )
    return errors


def client_contract_errors(db: ZoneDatabase, feed: int = DEFAULT_FEED) -> list[str]:
    """Reasons the published clients on ``feed`` could not consume ``db``.

    Delegates to `src/client_contract.py`, which reads `contracts/*.json` — the
    transcribed decode surface of every client actually in the stores. This is
    the fleet's only protection: an app-side fix cannot reach installs that
    already exist, so a violation here is a hard publish failure rather than a
    warning. See `scrapers/CLAUDE.md` "Never serve data a published client
    can't parse".

    Checked against the **wire form** (`exclude_none=True`), not the model: a
    null field is omitted from the JSON entirely, and an omitted key is exactly
    what fails the iOS 1.x decode.
    """
    payload = json.loads(db.model_dump_json(exclude_none=True))
    try:
        return contract_violations(payload, feed=feed)
    except ContractError as exc:
        # A broken/missing contract must fail the publish, never wave it
        # through: "no rules loaded" would otherwise read as "no violations".
        return [f"client contract could not be evaluated: {exc}"]




def write_target_dir(db: ZoneDatabase, dir_: Path) -> dict[int, str]:
    """Write every served feed into ``dir_`` for live serving.

    Each feed gets its own zones/version pair and its own snapshot history —
    feed 1 keeps the unsuffixed names it has always had. Returns the previous
    hash per feed (empty string where there was none).
    """
    dir_.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    prev_hashes: dict[int, str] = {}
    for entry in served_feeds():
        prev_hashes[entry["version"]] = _write_feed(db, dir_, entry, ts)
    return prev_hashes


def _write_feed(db: ZoneDatabase, dir_: Path, entry: dict, ts: str) -> str:
    """Write one feed's zones + version files. Returns its previous hash."""
    feed = entry["version"]
    projected = project(db, feed)
    zones_path = dir_ / zones_filename(feed)
    version_path = dir_ / version_filename(feed)

    prev_hash = _read_prev_hash(version_path)
    new_text = projected.model_dump_json(indent=2, exclude_none=True)

    # Snapshot only on a genuine content change. Gate on the data hash, not the
    # file bytes: ``last_verified`` is re-stamped to today on every zone every run
    # (validator.merge_match), so a byte comparison would rotate a spurious
    # snapshot every cron run. ``db.hash`` excludes ``last_verified`` (HASH_EXCLUDE),
    # so it only differs when the zone data actually changed.
    if zones_path.exists() and prev_hash and projected.hash != prev_hash:
        shutil.copy2(zones_path, dir_ / snapshot_name(feed, ts))

    atomic_write_text(zones_path, new_text)

    version_meta = {
        "version": projected.version,
        "hash": projected.hash,
        "feed": feed,
        "min_app_version": MIN_APP_VERSION,
        "zone_count": len(projected.zones),
        "map_hash": None,
    }
    if is_unsupported(entry):
        # Present only while the feed is unsupported; clients read any non-zero
        # value as "tell the user to update". Absent is the supported state —
        # `"unsupported": 0` would be a third state nobody needs to handle.
        version_meta["unsupported"] = 1
    atomic_write_text(version_path, json.dumps(version_meta, indent=2) + "\n")

    snapshots = sorted(dir_.glob(snapshot_glob(feed)), reverse=True)
    for old in snapshots[SNAPSHOT_RETENTION:]:
        old.unlink()

    logger.info(
        "Wrote %d zones to %s (feed=%d, prev_hash=%s)",
        len(projected.zones), zones_path, feed, prev_hash or "(none)",
    )
    return prev_hash


def realign_existing(path: Path) -> ZoneDatabase:
    """Re-apply geometry alignment to an existing zones.json in place.

    Deterministic and network-free: loads the file, aligns each zone's
    centerline to its endpoints (recomputing ``distance_m`` from the arc),
    re-hashes, and writes it back — preserving the existing ``version``. Use
    this to retrofit the bundled snapshot without a full re-scrape (which would
    pull unrelated upstream changes). Schema is unchanged, so released clients
    keep parsing the result.
    """
    db = ZoneDatabase.model_validate_json(path.read_text(encoding="utf-8"))
    aligned = [align_centerline_to_endpoints(z) for z in db.zones]
    out = ZoneDatabase(version=db.version, zones=aligned).with_hash()
    atomic_write_text(path, out.model_dump_json(indent=2, exclude_none=True))
    logger.info("Realigned %d zones in %s (hash=%s)", len(out.zones), path, out.hash)
    return out


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
    out_group.add_argument(
        "--realign",
        type=Path,
        help="Network-free: re-apply geometry alignment to an existing "
             "zones.json in place (centerline -> endpoints, distance_m -> arc) "
             "and re-hash. Does not scrape.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.realign is not None:
        db = realign_existing(args.realign)
        print_summary(db)
        return

    start = time.monotonic()
    try:
        db = run_pipeline()
    except SourceFailure as e:
        # Re-log the concise per-source errors LAST: the Telegram failure
        # message tails cron.log, so these lines are what the operator sees.
        for err in e.errors:
            logger.error("Source failure: %s", err)
        logger.error(
            "%d of the zone data sources failed — refusing to write output, "
            "existing data left untouched",
            len(e.errors),
        )
        sys.exit(1)

    try:
        prev_counts: dict[int, int | None] = {}
        if args.target_dir is not None:
            for entry in served_feeds():
                feed = entry["version"]
                prev_counts[feed] = _read_version_meta(
                    args.target_dir / version_filename(feed)
                ).get("zone_count")

        # All-or-nothing across feeds: a half-updated /api is worse than a
        # uniformly stale one, so every feed is guarded before any is written.
        guard_errors = all_feeds_guard_errors(db, prev_counts)
    except (FeedError, ContractError) as exc:
        logger.error("Feed configuration: %s", exc)
        logger.error("Refusing to write output — existing data left untouched")
        sys.exit(1)

    if guard_errors:
        for err in guard_errors:
            logger.error("Publish guard: %s", err)
        logger.error(
            "Refusing to write output — existing data left untouched"
        )
        sys.exit(1)

    if args.target_dir is not None:
        prev_hash = write_target_dir(db, args.target_dir).get(DEFAULT_FEED, "")
    else:
        write_output(db, args.output or DEFAULT_OUTPUT)
        prev_hash = ""
    duration_s = int(time.monotonic() - start)

    print_summary(db)

    # Machine-readable result line for the cron wrapper. Reports feed 1 — the
    # cron's `state/last_hash` and the Telegram "changed?" line have always
    # tracked `/api/zones`, so read the hash off that feed rather than off the
    # canonical db, which need not be what feed 1 serves.
    served = project(db, DEFAULT_FEED)
    print(
        f"RESULT zone_count={len(served.zones)} hash={served.hash} "
        f"prev_hash={prev_hash or '-'} duration_s={duration_s}",
        file=sys.stdout,
    )


if __name__ == "__main__":
    main()
