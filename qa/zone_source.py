# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Which zone catalog the harness drives against, and how scenarios name a zone.

Two catalogs exist and they are not the same file:

* **bundled** — `backend/data/zones.json`, what a fresh install seeds from.
* **live** — what `/api/zones` serves, i.e. what every install syncs to.

The app runs the *synced* catalog, so a harness that builds its routes and
expected ids from the bundled file is describing a device that stopped existing
at the first sync. That gap is invisible until BG TOLL inserts a section
mid-road: zone ids are km-ordered per road, so every later id shifts, and a
scenario asserting `zone == "trakiya-01-east"` is suddenly asserting a different
stretch of motorway (nightly red from 2026-09-21, when Крушовица – Вакарел
became the new `trakiya-01`).

So the nightly drives the live catalog: `scenarios/live_zones.py` makes the
device sync it, downloads the same payload here and switches this module to the
snapshot. Everything that reads zone data in the suites goes through `path()` /
`zones_by_id()`, so it follows the switch.

Most scenarios select current geometry by properties in `zone_selection.py`.
Historical reproducers that need one *particular* stretch name it by an **anchor**
(`fixtures/zone_anchors.yaml`) — a point on the road plus a direction — and
`resolve()` turns that into whatever id the active catalog gives it today.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
ANCHORS_YAML = REPO_ROOT / "qa" / "fixtures" / "zone_anchors.yaml"
GPX_FIXTURES_DIR = REPO_ROOT / "qa" / "fixtures" / "gpx"
API_BASE = "https://srednabg.com/api"

# The build under test picks its data feed at compile time; the harness has to
# ask for the same one. Android's literal is the one parsed — the iOS twin
# (`BackendURLs.feedVersion`) is kept equal to it by contract.
_FEED_SOURCE = REPO_ROOT / "android" / "app" / "build.gradle.kts"
_FEED_RE = re.compile(r"^val zoneFeedVersion = (\d+)\s*$", re.MULTILINE)

# How far an anchor point may sit from the centerline it names. Generous next to
# GPS-grade centerlines, and still far below the distance between two sections.
ANCHOR_TOLERANCE_M = 100.0
_HTTP_TIMEOUT_S = 30.0
# Live GPX caches are keyed by catalog hash; drop the ones nothing has touched
# in this long so they don't pile up one directory per upstream data change.
_STALE_GPX_DIR_S = 14 * 24 * 3600


class ZoneAnchorError(LookupError):
    """An anchor doesn't name exactly one usable zone in the active catalog."""


@dataclass(frozen=True)
class Snapshot:
    """A downloaded copy of the served catalog."""

    path: Path
    version: str
    hash: str
    zone_count: int


_live: Optional[Snapshot] = None
# Parsed catalog, cached per (path, mtime) so ~80 bulk scenarios don't re-read
# the 1.4 MB file.
_zones_cache: dict[tuple[str, float], dict[str, dict]] = {}
_anchors_cache: Optional[dict[str, dict]] = None


# ───────────────────────────── active catalog ─────────────────────────────


def feed_version() -> int:
    m = _FEED_RE.search(_FEED_SOURCE.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError(f"no `val zoneFeedVersion = N` line in {_FEED_SOURCE}")
    return int(m.group(1))


def _feed_suffix() -> str:
    feed = feed_version()
    return "" if feed == 1 else f".{feed}"


def bundled_path() -> Path:
    """The single source of truth both apps bundle (see root CLAUDE.md)."""
    return REPO_ROOT / "backend" / "data" / f"zones{_feed_suffix()}.json"


def is_live() -> bool:
    return _live is not None


def path() -> Path:
    return _live.path if _live else bundled_path()


def gpx_dir() -> Path:
    """Where generated routes are cached. Live catalogs get a directory per
    content hash: the nightly's Android and iOS processes share this cache, and
    two catalogs in one directory would each delete the other's routes as stale.
    """
    if _live is None:
        return GPX_FIXTURES_DIR
    return GPX_FIXTURES_DIR / f"live-{_live.hash.rsplit(':', 1)[-1][:12]}"


def zones_by_id() -> dict[str, dict]:
    p = path()
    key = (str(p), p.stat().st_mtime)
    if key not in _zones_cache:
        _zones_cache.clear()
        data = json.loads(p.read_text(encoding="utf-8"))
        zones = data["zones"] if isinstance(data, dict) else data
        _zones_cache[key] = {z["id"]: z for z in zones}
    return _zones_cache[key]


def describe() -> str:
    """One line naming the data under test — printed at the top of a run."""
    if _live:
        return (f"live feed {feed_version()} — version {_live.version}, "
                f"{_live.zone_count} zones, {_live.hash}")
    return f"bundled {bundled_path().relative_to(REPO_ROOT)} — {len(zones_by_id())} zones"


# ───────────────────────────── the served feed ─────────────────────────────


def endpoint(name: str) -> str:
    """URL for `name` on this build's feed — `ZoneApi.endpointPath`'s rule."""
    return f"{API_BASE}/{name}{_feed_suffix()}"


def _get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_version() -> dict[str, Any]:
    """`/api/version` — the hash + scrape timestamp of what's being served."""
    return _get_json(endpoint("version"))


def validate_catalog(payload: dict) -> None:
    """Reject broken live data before selectors can turn it into missing coverage."""
    if not isinstance(payload, dict) or not payload.get("zones") or not isinstance(payload.get("hash"), str) or not payload["hash"]:
        raise ValueError("catalog must contain zones and a content hash")
    seen = set()

    def point(p):
        return (len(p) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p)
                and -90 <= p[0] <= 90 and -180 <= p[1] <= 180 and p != [0, 0])

    for z in payload["zones"]:
        try:
            zid = z["id"]
            if not isinstance(zid, str) or not zid or zid in seen:
                raise ValueError(f"empty or duplicate zone id: {zid!r}")
            seen.add(zid)
            if z["direction"] not in {"north", "south", "east", "west"}:
                raise ValueError(f"{zid}: invalid direction")
            if not isinstance(z["road"], str) or not z["road"]:
                raise ValueError(f"{zid}: invalid road")
            cl = z["centerline"]
            if len(cl) < 2 or not all(point(p) for p in cl) or len({tuple(p) for p in cl}) < 2:
                raise ValueError(f"{zid}: invalid centerline")
            if not all(point([z[e]["lat"], z[e]["lng"]]) for e in ("start", "end")):
                raise ValueError(f"{zid}: invalid endpoints")
            values = [z["distance_m"], *(z["speed_limits"][v] for v in ("car", "truck", "bus"))]
            if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in values):
                raise ValueError(f"{zid}: invalid distance or speed limit")
        except (KeyError, TypeError) as e:
            raise ValueError(f"malformed live zone: {z.get('id', '?') if isinstance(z, dict) else z}") from e


def read_snapshot(path: Path) -> Snapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_catalog(payload)
    return Snapshot(path=path, version=str(payload.get("version", "")),
                    hash=payload["hash"], zone_count=len(payload["zones"]))


def download_snapshot(dest: Path) -> Snapshot:
    """Download exactly what the clients download and save it to `dest`."""
    payload = _get_json(endpoint("zones"))
    validate_catalog(payload)
    zones = payload["zones"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, dest)
    return Snapshot(path=dest, version=str(payload.get("version", "")),
                    hash=str(payload["hash"]), zone_count=len(zones))


def use_snapshot(snapshot: Snapshot) -> None:
    """Make `snapshot` the catalog every later scenario is built from."""
    global _live
    _live = snapshot
    _prune_stale_gpx_dirs(keep=gpx_dir())


def use_bundled() -> None:
    global _live
    _live = None


def _prune_stale_gpx_dirs(*, keep: Path) -> None:
    cutoff = time.time() - _STALE_GPX_DIR_S
    for d in GPX_FIXTURES_DIR.glob("live-*"):
        if d != keep and d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)


# ───────────────────────────────── anchors ─────────────────────────────────


def _anchors() -> dict[str, dict]:
    global _anchors_cache
    if _anchors_cache is None:
        import yaml  # lazy: keeps this module importable by the stdlib-only tests
        _anchors_cache = yaml.safe_load(ANCHORS_YAML.read_text(encoding="utf-8"))["anchors"]
    return _anchors_cache


def _point_to_segment_m(lat: float, lng: float, a: list[float], b: list[float]) -> float:
    """Distance from a point to a segment, on a local flat projection — exact
    enough at the 100 m scale this is used for."""
    k_lat = 111_320.0
    k_lng = k_lat * math.cos(math.radians(lat))
    ax, ay = (a[1] - lng) * k_lng, (a[0] - lat) * k_lat
    bx, by = (b[1] - lng) * k_lng, (b[0] - lat) * k_lat
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
    return math.hypot(ax + t * dx, ay + t * dy)


def distance_to_centerline_m(lat: float, lng: float, centerline: list[list[float]]) -> float:
    if len(centerline) < 2:
        return math.inf
    return min(_point_to_segment_m(lat, lng, a, b)
               for a, b in zip(centerline, centerline[1:]))


def resolve(anchor: str, zones: Optional[dict[str, dict]] = None) -> str:
    """The id the active catalog (or `zones`) gives the stretch `anchor` names.

    Ids are deliberately not the key: they are km-ordered per road and renumber
    whenever a section is inserted upstream. A point on the carriageway plus its
    direction survives renumbering, renames and description typo fixes alike.
    """
    spec = _anchors().get(anchor)
    if spec is None:
        raise ZoneAnchorError(
            f"unknown zone anchor {anchor!r} — known: {', '.join(sorted(_anchors()))}")
    lat, lng = spec["near"]
    catalog = zones if zones is not None else zones_by_id()
    hits = [
        z for z in catalog.values()
        if z.get("direction") == spec["direction"]
        and distance_to_centerline_m(lat, lng, z.get("centerline") or []) <= ANCHOR_TOLERANCE_M
    ]
    if len(hits) != 1:
        found = ", ".join(z["id"] for z in hits) or "none"
        raise ZoneAnchorError(
            f"zone anchor {anchor!r} ({spec['direction']}bound at {lat}, {lng}) must match "
            f"exactly one zone, matched: {found}. The road changed upstream — re-point the "
            f"anchor in {ANCHORS_YAML.name}.")
    zone = hits[0]
    min_len = spec.get("min_length_m")
    if min_len is not None and zone.get("distance_m", 0) < min_len:
        raise ZoneAnchorError(
            f"zone anchor {anchor!r} now resolves to {zone['id']} "
            f"({zone.get('description')}, {zone.get('distance_m')} m), shorter than the "
            f"{min_len} m its scenarios are tuned for — the section was split upstream. "
            f"Re-point the anchor in {ANCHORS_YAML.name}.")
    return zone["id"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download and validate the live QA catalog")
    parser.add_argument("--download", required=True, type=Path)
    args = parser.parse_args()
    snap = download_snapshot(args.download)
    print(f"Saved {snap.zone_count} live zones: {snap.version}, {snap.hash}")
