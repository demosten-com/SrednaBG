# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Typed events parsed from app logcat output.

Each event has a `monotonic_ms` field — the wall-clock receive time as
recorded by the logcat observer, used by assertions for `within_s`
windows. The `raw` field carries the original logcat line so failure
reports can quote it verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Event:
    monotonic_ms: int
    raw: str


@dataclass(frozen=True)
class LocationUpdate(Event):
    lat: float
    lng: float
    speed_mps: float
    accuracy_m: float
    provider: str
    is_mock: bool


@dataclass(frozen=True)
class DisplaySpeed(Event):
    """Speed shown on Home's 'Now km/h' — the post-filter `point.speed` from
    `LocationTrackingService` after the inferred-vs-reported max() resolves.

    `raw_ms` is the un-gated `location.speed`; `acc_ms` is the GPS speed
    accuracy estimate at 68% confidence (NaN if the fix has no
    speedAccuracy). `reported_kmh` is post-accuracy-gate."""
    kmh: float
    inferred_kmh: float
    reported_kmh: float
    raw_ms: float
    acc_ms: float
    fix_age_ms: int
    fresh_fix: bool


@dataclass(frozen=True)
class ZoneStateChange(Event):
    """Fires on every detector update — derived from AudioAlertManager.kt:75.

    `prev` and `new` are short class names: Outside, InZone, Unmeasured,
    Exiting. Unmeasured means "inside a zone whose entry we never witnessed" —
    it is silent (no TTS), records no History row, and can never be followed by
    Exiting (it drops straight to Outside). See ZoneDetector.START_WITNESS_ARC_M.
    `zone` is the zone id when new is InZone/Unmeasured/Exiting, "-" when
    Outside.
    `speed_kmh` may be None if the detector hadn't seen a fix yet.
    """
    prev: str
    new: str
    zone: str
    speed_kmh: Optional[float]


@dataclass(frozen=True)
class TtsSpeak(Event):
    """Every utterance the TTS engine actually spoke (AudioAlertManager.kt:200).

    Lines like `speak: TTS not initialized, dropping: "..."` are NOT this
    event — see TtsDropped.
    """
    text: str


@dataclass(frozen=True)
class TtsDropped(Event):
    """TTS was asked to speak but engine wasn't ready."""
    text: str


@dataclass(frozen=True)
class TtsLeadIn(Event):
    """Android-only: a cold audio-focus session prepended silent lead-in before
    the words, so the AA/Bluetooth route-open delay can't clip the message start
    (AudioAlertManager.kt `speak: cold start, …ms lead-in`)."""
    lead_in_ms: int


@dataclass(frozen=True)
class TtsSuppressed(Event):
    """Exit TTS suppressed because entry was <5s ago (transient glitch guard)."""
    entry_age_ms: int


@dataclass(frozen=True)
class ProvisionalEntry(Event):
    """An entry announced from the detector's *candidate*, before confirmation.

    The engine will not open a traversal until the car covers
    ENTRY_CONFIRM_DISTANCE_M (300 m) along the centerline, but the announcement
    no longer waits for that — it fires when the candidate opens, which is up to
    a band-width *before* the entry camera. `outcome` is what became of it:

      * `announced`  — the candidate opened and the entry was spoken.
      * `suppressed` — the candidate's first fix projected past
        START_WITNESS_ARC_M, so it could only ever have confirmed as Unmeasured.
        This is the A3/Кочериново phantom's fate.
      * `confirmed`  — an announced candidate graduated into a traversal.
      * `abandoned`  — an announced candidate was dropped. The driver heard an
        entry that produced no History row. Rare by design; counted so we know
        how rare.
    """
    zone: str
    outcome: str


@dataclass(frozen=True)
class SyncResult(Event):
    """DebugSyncReceiver result. `action` is SYNC_MAP or SYNC_ZONES.

    `outcome` is one of: Updated, UpToDate, Failed, Skipped.
    """
    action: str
    outcome: str
    detail: str = ""


@dataclass(frozen=True)
class SettingChanged(Event):
    """DebugSettingsReceiver applied a setting (the receiver we add)."""
    key: str
    value: str


@dataclass(frozen=True)
class ZonesLoaded(Event):
    """ZoneRepository emitted a new zone list (LocationTrackingService.kt:119)."""
    count: int


@dataclass(frozen=True)
class ZonesDropped(Event):
    """The client refused zones it can't use — `ZoneSanitizer` on both platforms.

    Never emitted against healthy data, so *any* occurrence is a finding: the
    served (or bundled) catalog contains a zone with placeholder (0, 0)
    endpoints, an empty centerline, or no car limit. See
    `qa/scenarios/sync/zones_all_usable.py`.
    """
    count: int
    ids: list[str]
    origin: str


@dataclass(frozen=True)
class ZonesRepaired(Event):
    """The client had to substitute a missing truck/bus limit from `car`.

    Distinct from `ZonesDropped` and just as much a finding: the zone works
    fine on a current build, and the **1.x clients in the stores** have no such
    fallback — iOS 1.x fails the entire `/api/zones` decode on that payload.
    Without this event, QA on a current build passes on data that is bricking
    every published install.
    """
    count: int
    ids: list[str]
    origin: str


@dataclass(frozen=True)
class LocationSourceSelected(Event):
    """Which GPS source the app picked when tracking started — emitted on tag
    `SrednaBG.LocSrc` by the flavor-specific `createLocationSource()`.

    `source` is "fused" (gms flavor, FusedLocationProvider) or "system"
    (aosp flavor, or the gms flavor's LocationManager fallback). The QA
    harness's `--flavor` assertion checks this matches the installed build —
    a tripwire against the aosp/FOSS build accidentally re-linking GMS.
    """
    source: str


@dataclass(frozen=True)
class IntervalChanged(Event):
    """LocationTrackingService bumped GPS polling interval."""
    interval_ms: int


@dataclass(frozen=True)
class AutoStopped(Event):
    """Inactivity auto-stop fired — the tracking service is shutting down
    because no zone state transition happened within the configured threshold.

    `elapsed_s` is observed idle duration; `threshold_s` is the resolved
    threshold (auto_stop_hours * 3600 or debug_auto_stop_seconds, whichever
    is active). Emitted on tag `SrednaBG.Loc`.
    """
    elapsed_s: int
    threshold_s: int


@dataclass(frozen=True)
class HistoryDump(Event):
    """DebugControlReceiver `DUMP_HISTORY` — QA introspection of the History DB.

    `count` is the total stored traversals. When `count > 0` the remaining
    fields summarize the most-recently-exited record (`avg_kmh` is None when
    the traversal was too short to compute an average). All None when empty.
    Emitted on tag `DebugSettings`.
    """
    count: int
    zone: Optional[str] = None
    avg_kmh: Optional[float] = None
    sustained_min_kmh: Optional[float] = None
    sustained_max_kmh: Optional[float] = None
    over_limit: Optional[bool] = None
    limit_kmh: Optional[int] = None
    vehicle: Optional[str] = None


@dataclass(frozen=True)
class Crash(Event):
    """Anything from logcat -b crash, or an uncaught FATAL EXCEPTION."""
    process: str
    stack_head: str


@dataclass(frozen=True)
class Anr(Event):
    process: str
    reason: str


@dataclass(frozen=True)
class UnparsedLog(Event):
    """Catch-all for log lines we recognized as ours but didn't parse.

    Useful in failure reports — these can hint that the parser missed a
    new log format that the harness should learn.
    """
    tag: str
