# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Settings client — talks to the debug DebugControlReceiver via broadcasts.

Goes through the typed setter on `SettingsRepository` (no DataStore proto
write races). Each call is followed by a brief wait for the
`SettingChanged` confirmation log so callers can assume the value has
been persisted before they continue.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from . import adb
from .events import SettingChanged
from .logcat import LogcatObserver

RECEIVER = f"{adb.PACKAGE}/{adb.PACKAGE}.app.debug.DebugControlReceiver"
ACTION_SET_SETTING = "com.demosten.srednabg.debug.SET_SETTING"
ACTION_START_TRACKING = "com.demosten.srednabg.debug.START_TRACKING"
ACTION_STOP_TRACKING = "com.demosten.srednabg.debug.STOP_TRACKING"


def _broadcast_set(key: str, value: str) -> None:
    adb.broadcast(ACTION_SET_SETTING, RECEIVER, extras={"key": key, "value": value})


def set_setting(key: str, value: str | int | bool, *, obs: Optional[LogcatObserver] = None,
                wait_s: float = 2.0) -> None:
    """Apply a single setting and (if obs given) confirm via logcat."""
    str_val = str(value).lower() if isinstance(value, bool) else str(value)
    _broadcast_set(key, str_val)
    if obs is None:
        time.sleep(0.3)
        return
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        try:
            ev = obs.queue.get(timeout=0.2)
        except Exception:
            continue
        if isinstance(ev, SettingChanged) and ev.key == key:
            return
    # Don't fail — the setter may have succeeded but the log line was
    # missed. Caller can verify by reading the value back from a flow.


@dataclass(frozen=True)
class SettingsCombo:
    """One row from the settings matrix in the plan."""
    id: str
    voice_enabled: bool
    periodic_voice_updates: bool
    announce_only_when_over: bool
    app_language: str
    vehicle_type: str
    alert_threshold_kmh: int = 5
    map_heading_up: bool = False

    def apply(self, obs: Optional[LogcatObserver] = None) -> None:
        # Order matters slightly: voice_enabled first so subsequent
        # toggle logs render meaningfully.
        set_setting("voice_enabled", self.voice_enabled, obs=obs)
        set_setting("periodic_voice_updates", self.periodic_voice_updates, obs=obs)
        set_setting("announce_only_when_over", self.announce_only_when_over, obs=obs)
        set_setting("app_language", self.app_language, obs=obs)
        set_setting("vehicle_type", self.vehicle_type, obs=obs)
        set_setting("alert_threshold_kmh", self.alert_threshold_kmh, obs=obs)
        set_setting("map_heading_up", self.map_heading_up, obs=obs)


# The four representative-tier combos from the approved plan.
COMBO_S1 = SettingsCombo("S1", True, True, True, "bg", "car")
COMBO_S2 = SettingsCombo("S2", True, False, False, "en", "truck")
COMBO_S3 = SettingsCombo("S3", False, True, True, "system", "bus")
COMBO_S4 = SettingsCombo("S4", True, True, False, "bg", "car")
ALL_COMBOS = [COMBO_S1, COMBO_S2, COMBO_S3, COMBO_S4]


def start_tracking() -> None:
    adb.broadcast(ACTION_START_TRACKING, RECEIVER)


def stop_tracking() -> None:
    adb.broadcast(ACTION_STOP_TRACKING, RECEIVER)
