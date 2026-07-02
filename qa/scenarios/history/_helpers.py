# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Shared plumbing for the History scenarios.

Cross-platform: the assertions read the History DB via the active device's
`dump_history()` — a `DUMP_HISTORY` broadcast on Android, a `/history?action=dump`
HTTP call on iOS — both of which emit the identical `DUMP_HISTORY …` line on tag
`DebugSettings` (parsed into a `HistoryDump` event).
"""

from __future__ import annotations

import time

from ... import device as device_mod
from ... import settings as settings_mod
from ...drive import DrivePlan
from ..bulk_loader import BulkScenarioSpec, _ensure_gpx
from ...drive import parse_gpx

# trakiya-01-east: real-fixture-backed in the core unit tests and used by the
# smoke suite, car limit 140 km/h — a clean, well-behaved traversal to record.
ZONE_ID = "trakiya-01-east"
WITHIN_LIMIT_KMH = 120.0  # < 140 car limit → the record's verdict is "within".


def zone_plan(
    zone_id: str = ZONE_ID,
    speed_kmh: float = WITHIN_LIMIT_KMH,
    *,
    approach_km: float = 1.0,
    exit_km: float = 0.5,
    compression: float = 6.0,
) -> DrivePlan:
    """A compressed drive through one zone (approach → zone → exit)."""
    spec = BulkScenarioSpec(
        name=f"history.{zone_id}",
        zone_id=zone_id,
        speed_kmh=speed_kmh,
        approach_km=approach_km,
        exit_km=exit_km,
        compression=compression,
    )
    gpx = _ensure_gpx(spec)
    return parse_gpx(gpx).compressed(compression)


def begin_tracking(ctx, *, retention: str) -> None:
    """Foreground, pin the history retention, start tracking, settle."""
    device_mod.current().start_main()
    time.sleep(2.0)
    # Force car so the recorded limit/verdict is the 140 car limit.
    settings_mod.set_setting("vehicle_type", "car", obs=ctx.obs)
    settings_mod.set_setting("history_retention", retention, obs=ctx.obs)
    settings_mod.start_tracking()
    time.sleep(2.5)
    ctx.obs.clear()


def reset_history(ctx) -> None:
    """Purge existing history by toggling retention to 'none' and back.

    `SrednaBGApp` prunes on every retention change; 'none' triggers a full
    clear, so a following record count is deterministic.
    """
    settings_mod.set_setting("history_retention", "none", obs=ctx.obs)
    time.sleep(1.0)


def dump_after_settle(ctx, *, settle_s: float = 3.0) -> None:
    """Let the async record write land, then request a history dump.

    Clears the observer first so the following assertion sees only the fresh
    `DUMP_HISTORY` line. Both backends block until the app has emitted the line
    (Android `am broadcast`'s goAsync; iOS's synchronous HTTP round trip), so
    it is present by the time this returns.
    """
    time.sleep(settle_s)
    ctx.obs.clear()
    device_mod.current().dump_history()
