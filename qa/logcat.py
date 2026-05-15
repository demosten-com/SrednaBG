# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Logcat tail + parser. Pushes typed events from `events.py` onto a Queue.

The observer runs `adb logcat -v threadtime` filtered to our tags plus the
crash buffer in a background thread and parses each line. Test code reads
events from the queue with timeouts.

Anchored to log strings emitted by:
- LocationTrackingService.kt (tag SrednaBG.Loc) — onLocation, zones changed,
  requestLocationWithInterval, ensureLoaded
- AudioAlertManager.kt          (tag SrednaBG.TTS) — onZoneStateChanged,
  speak, suppressing exit
- DebugSyncReceiver.kt          (tag DebugSync)    — SYNC_X -> SyncResult.Y
- DebugSettingsReceiver.kt      (tag DebugSettings) — set <key>=<value>
"""

from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from . import adb
from .events import (
    Anr,
    Crash,
    DisplaySpeed,
    Event,
    IntervalChanged,
    LocationUpdate,
    SettingChanged,
    SyncResult,
    TtsDropped,
    TtsSpeak,
    TtsSuppressed,
    UnparsedLog,
    ZoneStateChange,
    ZonesLoaded,
)

TAGS = ["SrednaBG.Loc", "SrednaBG.LocSrc", "SrednaBG.TTS", "DebugSync", "DebugSettings"]

# threadtime format: 04-16 14:23:45.123 12345 12345 D SrednaBG.Loc: message
_LINE_RE = re.compile(
    r"^(?P<date>\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\s+"
    r"\d+\s+\d+\s+(?P<level>[VDIWEF])\s+(?P<tag>\S+?)\s*:\s*(?P<msg>.*)$"
)

_LOC_RE = re.compile(
    r"onLocation: lat=(?P<lat>-?\d+\.?\d*) lng=(?P<lng>-?\d+\.?\d*) "
    r"speed=(?P<speed>-?\d+\.?\d*) accuracy=(?P<acc>-?\d+\.?\d*) "
    r"provider=(?P<prov>\S+) mock=(?P<mock>true|false)"
)

_DISPLAY_SPEED_RE = re.compile(
    r"displaySpeed: kmh=(?P<kmh>-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"inferredKmh=(?P<inferred>-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"reportedKmh=(?P<reported>-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"rawMs=(?P<rawms>-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"accMs=(?P<accms>NaN|-?\d+\.?\d*(?:[eE]-?\d+)?) "
    r"fixAgeMs=(?P<age>-?\d+) "
    r"fresh=(?P<fresh>true|false)"
)

_STATE_RE = re.compile(
    r"onZoneStateChanged prev=(?P<prev>\w+) new=(?P<new>\w+) "
    r"zone=(?P<zone>\S+) speed=(?P<speed>\S+)"
)

_SPEAK_RE = re.compile(r'^speak: "(?P<text>.*)"$')
_SPEAK_DROPPED_RE = re.compile(r'^speak: TTS not initialized, dropping: "(?P<text>.*)"$')
_SUPPRESS_RE = re.compile(r"suppressing exit TTS — entry was (?P<age>\d+)ms ago")
_ZONES_RE = re.compile(r"zones changed \(n=(?P<n>\d+)\)")
_INTERVAL_RE = re.compile(r"requestLocationWithInterval intervalMs=(?P<i>\d+)")
_SYNC_RE = re.compile(
    r"(?P<action>[\w.]+\.debug\.SYNC_\w+) -> (?:SyncResult\.)?(?P<outcome>\w+)(?:\((?P<detail>.*)\))?"
)
_SETTING_RE = re.compile(r"set (?P<key>\w+)=(?P<value>.+)$")


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def parse_line(raw: str) -> Optional[Event]:
    """Parse one logcat line into a typed event. Returns None for lines
    that match a tag we listen to but no known message format — those
    surface as `UnparsedLog`.

    Lines that don't match the threadtime format are returned as None
    (silently skipped).
    """
    m = _LINE_RE.match(raw)
    if not m:
        return None
    tag = m.group("tag")
    msg = m.group("msg")
    ts = _now_ms()

    if tag == "SrednaBG.Loc":
        ml = _LOC_RE.search(msg)
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
        md = _DISPLAY_SPEED_RE.search(msg)
        if md:
            return DisplaySpeed(
                monotonic_ms=ts,
                raw=raw,
                kmh=float(md.group("kmh")),
                inferred_kmh=float(md.group("inferred")),
                reported_kmh=float(md.group("reported")),
                raw_ms=float(md.group("rawms")),
                acc_ms=float(md.group("accms")),  # accepts "NaN"
                fix_age_ms=int(md.group("age")),
                fresh_fix=md.group("fresh") == "true",
            )
        mz = _ZONES_RE.search(msg)
        if mz:
            return ZonesLoaded(monotonic_ms=ts, raw=raw, count=int(mz.group("n")))
        mi = _INTERVAL_RE.search(msg)
        if mi:
            return IntervalChanged(monotonic_ms=ts, raw=raw, interval_ms=int(mi.group("i")))
        return UnparsedLog(monotonic_ms=ts, raw=raw, tag=tag)

    if tag == "SrednaBG.TTS":
        ms = _STATE_RE.search(msg)
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
        msd = _SPEAK_DROPPED_RE.match(msg)
        if msd:
            return TtsDropped(monotonic_ms=ts, raw=raw, text=msd.group("text"))
        msp = _SPEAK_RE.match(msg)
        if msp:
            return TtsSpeak(monotonic_ms=ts, raw=raw, text=msp.group("text"))
        msu = _SUPPRESS_RE.search(msg)
        if msu:
            return TtsSuppressed(monotonic_ms=ts, raw=raw, entry_age_ms=int(msu.group("age")))
        return UnparsedLog(monotonic_ms=ts, raw=raw, tag=tag)

    if tag == "DebugSync":
        msy = _SYNC_RE.search(msg)
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
        mst = _SETTING_RE.search(msg)
        if mst:
            return SettingChanged(
                monotonic_ms=ts, raw=raw, key=mst.group("key"), value=mst.group("value")
            )
        return UnparsedLog(monotonic_ms=ts, raw=raw, tag=tag)

    return None


@dataclass
class LogcatObserver:
    """Background logcat tail. `start()` then read events from `.queue`.

    `recent_lines` keeps the last N raw lines (any tag we listened to)
    for failure-report context. `crash_seen` is set true the moment we
    see a FATAL EXCEPTION or ANR pattern in any tag.
    """

    queue: "queue.Queue[Event]" = None  # type: ignore[assignment]
    proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
    thread: Optional[threading.Thread] = None
    recent_lines: list[str] = None  # type: ignore[assignment]
    max_recent: int = 400
    _stop: bool = False

    def __post_init__(self) -> None:
        if self.queue is None:
            self.queue = queue.Queue()
        if self.recent_lines is None:
            self.recent_lines = []

    def start(self) -> None:
        adb.clear_logcat()
        tag_args: list[str] = []
        for t in TAGS:
            tag_args += ["-s", f"{t}:V"]
        # `-s` already silences everything else; we additionally listen
        # for FATAL EXCEPTION which appears under various tags.
        cmd = [
            "adb", "logcat", "-v", "threadtime",
            *tag_args,
            "AndroidRuntime:E",  # uncaught Java exceptions
            "ActivityManager:W",  # ANR lines surface here
        ]
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        for raw in self.proc.stdout:
            if self._stop:
                break
            raw = raw.rstrip("\n")
            self._record_recent(raw)
            self._maybe_emit_crash(raw)
            ev = parse_line(raw)
            if ev:
                self.queue.put(ev)

    def _record_recent(self, raw: str) -> None:
        self.recent_lines.append(raw)
        if len(self.recent_lines) > self.max_recent:
            del self.recent_lines[0 : len(self.recent_lines) - self.max_recent]

    def _maybe_emit_crash(self, raw: str) -> None:
        if "FATAL EXCEPTION" in raw and adb.PACKAGE in raw:
            self.queue.put(Crash(monotonic_ms=_now_ms(), raw=raw, process=adb.PACKAGE, stack_head=raw))
        elif "ANR in " in raw and adb.PACKAGE in raw:
            self.queue.put(Anr(monotonic_ms=_now_ms(), raw=raw, process=adb.PACKAGE, reason=raw))

    def stop(self) -> None:
        self._stop = True
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def drain(self) -> Iterable[Event]:
        """Yield all events currently buffered (non-blocking)."""
        while True:
            try:
                yield self.queue.get_nowait()
            except queue.Empty:
                return

    def clear(self) -> None:
        """Discard buffered events and recent lines. Use before a scenario."""
        list(self.drain())
        self.recent_lines.clear()
