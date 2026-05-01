# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Shared helpers for the edge-scenario family.

These scenarios construct DrivePlans with custom shapes (stops, gaps,
direction reversals) rather than going through the bulk YAML loader.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ... import settings as settings_mod
from ...assertions import expect_crash_free
from ...drive import DrivePlan, parse_gpx
from ...runner import RunContext
from ..bulk_loader import _ensure_gpx, BulkScenarioSpec

REPO_ROOT = Path(__file__).resolve().parents[3]
ZONES_JSON = REPO_ROOT / "scrapers" / "data" / "zones.json"


def load_zone(zone_id: str) -> dict[str, Any]:
    data = json.loads(ZONES_JSON.read_text(encoding="utf-8"))
    for z in data["zones"]:
        if z["id"] == zone_id:
            return z
    raise ValueError(f"zone not found: {zone_id}")


def base_plan(zone_id: str, *, speed_kmh: float = 130, approach_km: float = 2,
              exit_km: float = 1, hz: float = 1.0) -> DrivePlan:
    """Generate or reuse a baseline GPX for the given zone, return the
    parsed DrivePlan (uncompressed)."""
    spec = BulkScenarioSpec(
        name=f"{zone_id}-edge", zone_id=zone_id, speed_kmh=speed_kmh,
        approach_km=approach_km, exit_km=exit_km, hz=hz,
    )
    gpx = _ensure_gpx(spec)
    return parse_gpx(gpx)


def scenario_setup(ctx: RunContext, *, settings_id: str = "S1") -> None:
    from ... import adb
    # MainActivity must be foregrounded before startForegroundService is
    # allowed under Android 12+ background-start restrictions.
    adb.start_main()
    time.sleep(2.0)
    combo = next(c for c in settings_mod.ALL_COMBOS if c.id == settings_id)
    combo.apply(ctx.obs)
    settings_mod.start_tracking()
    time.sleep(2.5)
    ctx.obs.clear()


def scenario_teardown(ctx: RunContext) -> None:
    settings_mod.stop_tracking()
    expect_crash_free(ctx.obs)
