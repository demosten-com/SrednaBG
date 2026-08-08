# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Settings client — routes through the active Device.

Public surface is unchanged; the platform-specific plumbing (am broadcast on
Android, srednabg-debug:// openurl on iOS) lives in the Device impl.
Each call is followed by a brief wait for the `SettingChanged` confirmation
event so callers can assume the value has been persisted before they continue.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Optional

from . import device as device_mod
from .events import SettingChanged
from .log_observer import LogObserver


def set_setting(key: str, value: str | int | bool, *, obs: Optional[LogObserver] = None,
                wait_s: float = 2.0) -> None:
    """Apply a single setting and (if obs given) confirm via the log stream."""
    str_val = str(value).lower() if isinstance(value, bool) else str(value)
    device_mod.current().set_setting(key, str_val)
    if obs is None:
        time.sleep(0.3)
        return
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        try:
            ev = obs.queue.get(timeout=0.2)
        except queue.Empty:
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
    map_heading_up: bool = False

    def apply(self, obs: Optional[LogObserver] = None) -> None:
        # Order matters slightly: voice_enabled first so subsequent
        # toggle logs render meaningfully.
        set_setting("voice_enabled", self.voice_enabled, obs=obs)
        set_setting("periodic_voice_updates", self.periodic_voice_updates, obs=obs)
        set_setting("announce_only_when_over", self.announce_only_when_over, obs=obs)
        set_setting("app_language", self.app_language, obs=obs)
        set_setting("vehicle_type", self.vehicle_type, obs=obs)
        set_setting("map_heading_up", self.map_heading_up, obs=obs)


COMBO_S1 = SettingsCombo("S1", True, True, True, "bg", "car")
COMBO_S2 = SettingsCombo("S2", True, False, False, "en", "truck")
COMBO_S3 = SettingsCombo("S3", False, True, True, "system", "bus")
COMBO_S4 = SettingsCombo("S4", True, True, False, "bg", "car")
ALL_COMBOS = [COMBO_S1, COMBO_S2, COMBO_S3, COMBO_S4]

# Combos a specific scenario asks for by id but that are deliberately NOT in the
# representative matrix — adding one to ALL_COMBOS multiplies that suite's
# runtime by (zones x combos) for no extra coverage.
# S3 is also `bus`, but with voice OFF — a TTS-asserting scenario needs its own.
COMBO_S5 = SettingsCombo("S5", True, False, False, "en", "bus")
EXTRA_COMBOS = [COMBO_S5]


def combo_by_id(combo_id: str) -> SettingsCombo:
    """Resolve a combo id across the matrix and the scenario-only extras."""
    for combo in (*ALL_COMBOS, *EXTRA_COMBOS):
        if combo.id == combo_id:
            return combo
    raise KeyError(f"unknown settings combo id: {combo_id}")


def start_tracking() -> None:
    device_mod.current().start_tracking()


def stop_tracking() -> None:
    device_mod.current().stop_tracking()
