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

from dataclasses import dataclass, field
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
class ZoneStateChange(Event):
    """Fires on every detector update — derived from AudioAlertManager.kt:75.

    `prev` and `new` are short class names: Outside, InZone, Exiting.
    `zone` is the zone id when new is InZone/Exiting, "-" when Outside.
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
class TtsSuppressed(Event):
    """Exit TTS suppressed because entry was <5s ago (transient glitch guard)."""
    entry_age_ms: int


@dataclass(frozen=True)
class SyncResult(Event):
    """DebugSyncReceiver result. `action` is SYNC_MAP or SYNC_ZONES.

    `outcome` is one of: Updated, UpToDate, Failed.
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
class IntervalChanged(Event):
    """LocationTrackingService bumped GPS polling interval."""
    interval_ms: int


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
