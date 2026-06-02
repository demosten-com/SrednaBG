# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""AndroidDevice — adb-based backend.

Delegates to the lower-level `qa.adb` helpers (which still own the
`adb` CLI specifics — constants, _run, shell, shell_check). The Device
class here just gives the runner / scenarios a platform-agnostic surface.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from qa import adb
from qa.device import (
    Device,
    MAP_STYLE_FILES,
    MAP_STYLE_PLACEHOLDERS,
    MapIntegrityResult,
)

PACKAGE = adb.PACKAGE
DEBUG_CONTROL_RECEIVER = f"{PACKAGE}/{PACKAGE}.app.debug.DebugControlReceiver"
DEBUG_SYNC_RECEIVER = f"{PACKAGE}/{PACKAGE}.app.debug.DebugSyncReceiver"

ACTION_SET_SETTING = "com.demosten.srednabg.debug.SET_SETTING"
ACTION_START_TRACKING = "com.demosten.srednabg.debug.START_TRACKING"
ACTION_STOP_TRACKING = "com.demosten.srednabg.debug.STOP_TRACKING"
ACTION_SYNC_MAP = "com.demosten.srednabg.debug.SYNC_MAP"
ACTION_SYNC_ZONES = "com.demosten.srednabg.debug.SYNC_ZONES"
ACTION_FEED_POINT = "com.demosten.srednabg.debug.FEED_POINT"

PROD_VERSION_URL = "https://srednabg.com/api/version"


class AndroidDevice(Device):
    @property
    def platform(self) -> str:
        return "android"

    @property
    def package_id(self) -> str:
        return PACKAGE

    # ── lifecycle ───────────────────────────────────────────────────────────
    def require_device(self) -> str:
        return adb.require_one_device()

    def package_installed(self) -> bool:
        return adb.package_installed()

    def install_app(self, path: Path) -> None:
        adb.install_apk(path)

    def force_stop(self) -> None:
        adb.force_stop()

    def start_main(self) -> None:
        adb.start_main()

    def start_tracking_service(self) -> None:
        adb.start_tracking_service()

    def app_running(self) -> bool:
        return adb.app_running()

    def grant_runtime_permissions(self) -> None:
        adb.grant_runtime_permissions()

    def mute_audio(self) -> None:
        adb.mute_audio()

    # ── location injection ──────────────────────────────────────────────────
    def geo_fix(self, lng: float, lat: float) -> None:
        adb.geo_fix(lng, lat)

    def feed_point(self, lat: float, lng: float, speed_ms: float,
                   bearing: float | None = None) -> None:
        extras = {
            "lat": f"{lat:.7f}",
            "lng": f"{lng:.7f}",
            "speed_ms": f"{speed_ms:.3f}",
        }
        if bearing is not None:
            extras["bearing"] = f"{bearing:.2f}"
        adb.broadcast(ACTION_FEED_POINT, DEBUG_CONTROL_RECEIVER, extras=extras)

    # ── debug surface ───────────────────────────────────────────────────────
    def set_setting(self, key: str, value: str) -> None:
        adb.broadcast(ACTION_SET_SETTING, DEBUG_CONTROL_RECEIVER,
                      extras={"key": key, "value": value})

    def set_zoom_override(self, zoom: float | None) -> None:
        self.set_setting("map_zoom_override", "" if zoom is None else f"{zoom}")

    def start_tracking(self) -> None:
        adb.broadcast(ACTION_START_TRACKING, DEBUG_CONTROL_RECEIVER)

    def stop_tracking(self) -> None:
        adb.broadcast(ACTION_STOP_TRACKING, DEBUG_CONTROL_RECEIVER)

    def force_sync_zones(self) -> None:
        adb.broadcast(ACTION_SYNC_ZONES, DEBUG_SYNC_RECEIVER)

    def force_sync_map(self) -> None:
        adb.broadcast(ACTION_SYNC_MAP, DEBUG_SYNC_RECEIVER)

    # ── network gating ──────────────────────────────────────────────────────
    def go_offline(self) -> None:
        rc, _, err = adb.shell_check("cmd connectivity airplane-mode enable")
        if rc != 0:
            raise RuntimeError(f"failed to enable airplane mode: {err.strip()}")
        time.sleep(1.5)

    def go_online(self) -> None:
        rc, _, err = adb.shell_check("cmd connectivity airplane-mode disable")
        if rc != 0:
            raise RuntimeError(f"failed to disable airplane mode: {err.strip()}")
        import urllib.request
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(PROD_VERSION_URL, timeout=2.0) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
            time.sleep(0.5)

    # ── cosmetic chrome (screenshot harness) ────────────────────────────────
    def set_system_appearance(self, mode: str) -> None:
        if mode not in ("light", "dark"):
            raise ValueError(f"mode must be 'light' or 'dark', got {mode!r}")
        # `cmd uimode night yes|no|auto` is the Android 10+ surface for
        # forcing the system-wide dark/light theme.
        night = "yes" if mode == "dark" else "no"
        adb.shell(f"cmd uimode night {night}")

    def override_status_bar(self) -> None:
        # SystemUI demo mode locks the status bar to a clean App-Store
        # look: 9:41 clock, 100% battery, full wifi, no notifications.
        # Requires `sysui_demo_allowed=1`. Granted on the emulator's
        # shell user by default; on a physical device the user has to
        # `adb shell pm grant com.android.shell android.permission.DUMP`.
        adb.shell("settings put global sysui_demo_allowed 1")
        adb.shell("am broadcast -a com.android.systemui.demo -e command enter")
        adb.shell("am broadcast -a com.android.systemui.demo -e command clock -e hhmm 0941")
        adb.shell("am broadcast -a com.android.systemui.demo -e command battery "
                  "-e level 100 -e plugged false")
        adb.shell("am broadcast -a com.android.systemui.demo -e command network "
                  "-e wifi show -e level 4")
        adb.shell("am broadcast -a com.android.systemui.demo -e command network "
                  "-e mobile show -e level 4 -e datatype lte")
        adb.shell("am broadcast -a com.android.systemui.demo -e command notifications "
                  "-e visible false")

    def clear_status_bar_override(self) -> None:
        adb.shell("am broadcast -a com.android.systemui.demo -e command exit")

    # ── inspection ──────────────────────────────────────────────────────────
    def screencap(self, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            subprocess.run(
                [adb._adb(), "exec-out", "screencap", "-p"],
                stdout=f, check=True, timeout=15,
            )
        return dest

    def crash_buffer(self) -> str:
        return adb.crash_buffer()

    def clear_crash_buffer(self) -> None:
        adb.clear_crash_buffer()

    def check_map_integrity(self) -> MapIntegrityResult:
        files_dir = f"/data/data/{PACKAGE}/files/map"
        mbtiles_present = adb.file_exists_in_app(PACKAGE, f"{files_dir}/bulgaria.mbtiles")

        # The bundle ships a light + dark style; both must be installed and
        # placeholder-rewritten. `style_present` is the AND across them.
        styles_present = True
        placeholders: list[str] = []
        for style_name in MAP_STYLE_FILES:
            style_path = f"{files_dir}/{style_name}"
            if not adb.file_exists_in_app(PACKAGE, style_path):
                styles_present = False
                continue
            try:
                content = adb.run_as_read(PACKAGE, style_path)
                for ph in MAP_STYLE_PLACEHOLDERS:
                    if ph in content and ph not in placeholders:
                        placeholders.append(ph)
            except Exception:
                pass

        size = 0
        if mbtiles_present:
            rc, out, _ = adb.shell_check(
                f"run-as {PACKAGE} stat -c %s {files_dir}/bulgaria.mbtiles"
            )
            if rc == 0:
                try:
                    size = int(out.strip())
                except ValueError:
                    size = 0
        return MapIntegrityResult(
            style_present=styles_present,
            mbtiles_present=mbtiles_present,
            placeholders_remaining=placeholders,
            mbtiles_size_bytes=size,
        )
