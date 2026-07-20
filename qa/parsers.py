# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Log line parsers — the regexes that turn an app log message into a typed
Event from `qa.events`.

Both the Android (`adb logcat -v threadtime`) and iOS (`xcrun simctl spawn
booted log stream --style ndjson`) observers feed `parse_message(tag, msg)`
once they've reduced their platform's line format to a (tag, message) pair.

Anchored to log strings emitted by the Android app:
- LocationTrackingService.kt (tag SrednaBG.Loc) — onLocation, displaySpeed,
  zones changed, requestLocationWithInterval
- AudioAlertManager.kt          (tag SrednaBG.TTS) — onZoneStateChanged,
  speak, suppressing exit
- DebugSyncReceiver.kt          (tag DebugSync)    — SYNC_X -> SyncResult.Y
- DebugSettingsReceiver.kt      (tag DebugSettings) — set <key>=<value>

The iOS app emits the same line bodies under matching os_log categories
(`SrednaBG.Loc`, `SrednaBG.TTS`, `DebugSync`, `DebugSettings`); see
ios/Packages/SrednaBGTracking and SrednaBGData.
"""

from __future__ import annotations

import re
import time
from typing import Optional

from .events import (
    AutoStopped,
    DisplaySpeed,
    Event,
    HistoryDump,
    IntervalChanged,
    LocationSourceSelected,
    LocationUpdate,
    SettingChanged,
    SyncResult,
    TtsDropped,
    TtsLeadIn,
    TtsSpeak,
    TtsSuppressed,
    UnparsedLog,
    ZoneStateChange,
    ZonesLoaded,
)

TAGS = ["SrednaBG.Loc", "SrednaBG.LocSrc", "SrednaBG.TTS", "DebugSync", "DebugSettings"]

# threadtime format: 04-16 14:23:45.123 12345 12345 D SrednaBG.Loc: message
LINE_RE = re.compile(
    r"^(?P<date>\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\s+"
    r"\d+\s+\d+\s+(?P<level>[VDIWEF])\s+(?P<tag>\S+?)\s*:\s*(?P<msg>.*)$"
)

LOC_RE = re.compile(
    r"onLocation: lat=(?P<lat>-?\d+\.?\d*) lng=(?P<lng>-?\d+\.?\d*) "
    r"speed=(?P<speed>-?\d+\.?\d*) accuracy=(?P<acc>-?\d+\.?\d*) "
    r"provider=(?P<prov>\S+) mock=(?P<mock>true|false)"
)

DISPLAY_SPEED_RE = re.compile(
    r"displaySpeed: kmh=(?P<kmh>-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"inferredKmh=(?P<inferred>-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"reportedKmh=(?P<reported>-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"rawMs=(?P<rawms>-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"accMs=(?P<accms>NaN|-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"fixAgeMs=(?P<age>-?\d+) "
    r"fresh=(?P<fresh>true|false)"
)

STATE_RE = re.compile(
    r"onZoneStateChanged prev=(?P<prev>\w+) new=(?P<new>\w+) "
    r"zone=(?P<zone>\S+) speed=(?P<speed>\S+)"
)

SPEAK_RE = re.compile(r'^speak: "(?P<text>.*)"$')
SPEAK_DROPPED_RE = re.compile(r'^speak: TTS not initialized, dropping: "(?P<text>.*)"$')
LEAD_IN_RE = re.compile(r"^speak: cold start, (?P<ms>\d+)ms lead-in$")
SUPPRESS_RE = re.compile(r"suppressing exit TTS — entry was (?P<age>\d+)ms ago")
ZONES_RE = re.compile(r"zones changed \(n=(?P<n>\d+)\)")
INTERVAL_RE = re.compile(r"requestLocationWithInterval intervalMs=(?P<i>\d+)")
SYNC_RE = re.compile(
    r"(?P<action>[\w.]+\.debug\.SYNC_\w+) -> (?:SyncResult\.)?(?P<outcome>\w+)(?:\((?P<detail>.*)\))?"
)
SETTING_RE = re.compile(r"set (?P<key>\w+)=(?P<value>.+)$")
# DebugControlReceiver DUMP_HISTORY: count always present; the latest-record
# summary fields only when count > 0 (else `latest=none`).
HISTORY_DUMP_RE = re.compile(
    r"DUMP_HISTORY count=(?P<count>\d+)"
    r"(?: zone=(?P<zone>\S+) avg=(?P<avg>\S+) min=(?P<min>\S+) max=(?P<max>\S+) "
    r"over=(?P<over>true|false) limit=(?P<limit>\d+) vehicle=(?P<vehicle>\S+) "
    r"entry=(?P<entry>\d+) exit=(?P<exit>\d+))?"
)
# Emitted by the flavor-specific createLocationSource() (LocationSourceFactory.kt
# in src/aosp + src/gms). "Selecting FusedLocationSource" / "Selecting
# SystemLocationSource …" — the trailing parenthetical detail is ignored.
LOC_SRC_RE = re.compile(r"Selecting (?P<src>Fused|System)LocationSource")
AUTO_STOP_RE = re.compile(
    r"auto-stop: idle for (?P<elapsed>\d+)s \(threshold=(?P<threshold>\d+)s\)"
)


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def parse_message(tag: str, msg: str, raw: str) -> Optional[Event]:
    """Map a (tag, message) pair to a typed Event.

    `raw` is the original line for failure reports. Returns None if the
    tag is unknown, or `UnparsedLog` if the tag matched but no message
    regex did.
    """
    ts = _now_ms()

    if tag == "SrednaBG.Loc":
        ml = LOC_RE.search(msg)
        if ml:
            return LocationUpdate(
                monotonic_ms=ts,
                raw=raw,
                lat=float(ml.group("lat")),
                lng=float(ml.group("lng")),
                speed_mps=float(ml.group("speed")),
                accuracy_m=float(ml.group("acc")),
                provider=ml.group("prov"),
                is_mock=ml.group("mock") == "true",
            )
        md = DISPLAY_SPEED_RE.search(msg)
        if md:
            return DisplaySpeed(
                monotonic_ms=ts,
                raw=raw,
                kmh=float(md.group("kmh")),
                inferred_kmh=float(md.group("inferred")),
                reported_kmh=float(md.group("reported")),
                raw_ms=float(md.group("rawms")),
                acc_ms=float(md.group("accms")),
                fix_age_ms=int(md.group("age")),
                fresh_fix=md.group("fresh") == "true",
            )
        mz = ZONES_RE.search(msg)
        if mz:
            return ZonesLoaded(monotonic_ms=ts, raw=raw, count=int(mz.group("n")))
        mi = INTERVAL_RE.search(msg)
        if mi:
            return IntervalChanged(monotonic_ms=ts, raw=raw, interval_ms=int(mi.group("i")))
        mas = AUTO_STOP_RE.search(msg)
        if mas:
            return AutoStopped(
                monotonic_ms=ts,
                raw=raw,
                elapsed_s=int(mas.group("elapsed")),
                threshold_s=int(mas.group("threshold")),
            )
        return UnparsedLog(monotonic_ms=ts, raw=raw, tag=tag)

    if tag == "SrednaBG.LocSrc":
        msrc = LOC_SRC_RE.search(msg)
        if msrc:
            return LocationSourceSelected(
                monotonic_ms=ts,
                raw=raw,
                source="fused" if msrc.group("src") == "Fused" else "system",
            )
        return UnparsedLog(monotonic_ms=ts, raw=raw, tag=tag)

    if tag == "SrednaBG.TTS":
        ms = STATE_RE.search(msg)
        if ms:
            sp = ms.group("speed")
            speed_kmh: Optional[float]
            try:
                speed_kmh = float(sp)
            except ValueError:
                speed_kmh = None
            return ZoneStateChange(
                monotonic_ms=ts,
                raw=raw,
                prev=ms.group("prev"),
                new=ms.group("new"),
                zone=ms.group("zone"),
                speed_kmh=speed_kmh,
            )
        msd = SPEAK_DROPPED_RE.match(msg)
        if msd:
            return TtsDropped(monotonic_ms=ts, raw=raw, text=msd.group("text"))
        mli = LEAD_IN_RE.match(msg)
        if mli:
            return TtsLeadIn(monotonic_ms=ts, raw=raw, lead_in_ms=int(mli.group("ms")))
        msp = SPEAK_RE.match(msg)
        if msp:
            return TtsSpeak(monotonic_ms=ts, raw=raw, text=msp.group("text"))
        msu = SUPPRESS_RE.search(msg)
        if msu:
            return TtsSuppressed(monotonic_ms=ts, raw=raw, entry_age_ms=int(msu.group("age")))
        return UnparsedLog(monotonic_ms=ts, raw=raw, tag=tag)

    if tag == "DebugSync":
        msy = SYNC_RE.search(msg)
        if msy:
            return SyncResult(
                monotonic_ms=ts,
                raw=raw,
                action=msy.group("action").rsplit(".", 1)[-1],
                outcome=msy.group("outcome"),
                detail=msy.group("detail") or "",
            )
        return UnparsedLog(monotonic_ms=ts, raw=raw, tag=tag)

    if tag == "DebugSettings":
        mh = HISTORY_DUMP_RE.search(msg)
        if mh:
            avg_raw = mh.group("avg")
            return HistoryDump(
                monotonic_ms=ts,
                raw=raw,
                count=int(mh.group("count")),
                zone=mh.group("zone"),
                avg_kmh=None if avg_raw in (None, "null") else float(avg_raw),
                sustained_min_kmh=None if mh.group("min") is None else float(mh.group("min")),
                sustained_max_kmh=None if mh.group("max") is None else float(mh.group("max")),
                over_limit=None if mh.group("over") is None else mh.group("over") == "true",
                limit_kmh=None if mh.group("limit") is None else int(mh.group("limit")),
                vehicle=mh.group("vehicle"),
            )
        mst = SETTING_RE.search(msg)
        if mst:
            return SettingChanged(
                monotonic_ms=ts, raw=raw, key=mst.group("key"), value=mst.group("value")
            )
        return UnparsedLog(monotonic_ms=ts, raw=raw, tag=tag)

    return None


def parse_threadtime_line(raw: str) -> Optional[Event]:
    """Android adb-logcat-threadtime line → Event.

    Returns None for lines that don't match the threadtime format (silently
    skipped — they may be header lines or stderr noise).
    """
    m = LINE_RE.match(raw)
    if not m:
        return None
    return parse_message(m.group("tag"), m.group("msg"), raw)
