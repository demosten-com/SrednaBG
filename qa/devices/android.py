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

import re
import subprocess
import time
import xml.etree.ElementTree as ET
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
ACTION_SEED_HISTORY = "com.demosten.srednabg.debug.SEED_HISTORY"

# Compose testTag surfaced as a resource-id (the list's parent sets
# `testTagsAsResourceId`); the QA `ui.history_show_on_map` scenario uses the same.
HISTORY_ROW_RESOURCE_ID = "history-row"
# Only the detail screen carries the "Show on map" toolbar action — used to tell
# "detail is open" from "list is showing".
HISTORY_DETAIL_RESOURCE_ID = "history-show-on-map"

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
                   bearing: float | None = None,
                   time_ms: int | None = None,
                   accuracy_m: float | None = None) -> None:
        extras = {
            "lat": f"{lat:.7f}",
            "lng": f"{lng:.7f}",
            "speed_ms": f"{speed_ms:.3f}",
        }
        if bearing is not None:
            extras["bearing"] = f"{bearing:.2f}"
        if time_ms is not None:
            extras["time_ms"] = str(time_ms)
        if accuracy_m is not None:
            extras["accuracy"] = f"{accuracy_m:.2f}"
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

    def dump_history(self) -> None:
        adb.dump_history()

    def seed_history(self, count: int) -> None:
        adb.broadcast(ACTION_SEED_HISTORY, DEBUG_CONTROL_RECEIVER,
                      extras={"count": str(count)})

    def ensure_history_list(self) -> None:
        # The detail screen is identified by its "Show on map" toolbar action;
        # the list has no such node. Back out (at most a couple of levels) so the
        # rows are addressable again.
        for _ in range(3):
            if self._find_node_by_resource_id(HISTORY_DETAIL_RESOURCE_ID) is None:
                return
            adb.shell("input keyevent 4")  # KEYCODE_BACK
            time.sleep(1.0)
        raise RuntimeError(
            "History detail still showing after 3 back presses — cannot reach the list"
        )

    def open_history_detail(self, select: str = "newest") -> None:
        # Rows carry the `history-row` test tag, surfaced as a resource-id
        # because the list's parent sets `testTagsAsResourceId`. Matching by tag
        # (not by the translatable row caption) keeps this locale-independent.
        # Poll — seeded rows arrive via a Room Flow emission a beat after the
        # tab switch.
        deadline = time.monotonic() + 15.0
        rows: list[tuple[tuple[int, int], int, int]] = []
        while time.monotonic() < deadline:
            rows = self._history_rows()
            if rows:
                break
            time.sleep(1.0)
        if not rows:
            raise RuntimeError(
                f"no {HISTORY_ROW_RESOURCE_ID!r} rows in the UI — is the History "
                f"tab showing and seeded?"
            )
        target = self._pick_history_row(rows, select)
        if target is None:
            raise RuntimeError(
                f"no history row matching select={select!r} among "
                f"{[(lim, avg) for _, lim, avg in rows]} (limit, average)"
            )
        x, y = target
        adb.shell(f"input tap {x} {y}")
        time.sleep(1.5)  # let the detail screen push + settle

    @staticmethod
    def _pick_history_row(
        rows: list[tuple[tuple[int, int], int, int]], select: str
    ) -> tuple[int, int] | None:
        """Centre of the row matching `select` — see VALID_OPEN_DETAIL."""
        if select == "newest":
            return rows[0][0]
        for center, limit, avg in rows:
            over = avg > limit
            if (select == "red") == over:
                return center
        return None

    def _history_rows(self) -> list[tuple[tuple[int, int], int, int]]:
        """[(centre, limit_kmh, avg_kmh)] per visible row, in list order.

        Both numbers are read as bare digits out of the row subtree — the badge
        limit comes first in document order, then the average. Digits are
        locale-independent, so this works in EN and BG without touching the
        translatable caption text.
        """
        root = self._dump_ui()
        if root is None:
            return []
        out: list[tuple[tuple[int, int], int, int]] = []
        for node in root.iter("node"):
            if node.attrib.get("resource-id") != HISTORY_ROW_RESOURCE_ID:
                continue
            center = self._bounds_center(node)
            nums = [
                int(t) for t in (d.attrib.get("text", "") for d in node.iter("node"))
                if t.isdigit()
            ]
            if center is None or len(nums) < 2:
                continue
            out.append((center, nums[0], nums[1]))
        return out

    @staticmethod
    def _dump_ui() -> "ET.Element | None":
        """Parsed accessibility tree, or None if the dump was unusable."""
        adb.shell("uiautomator dump /sdcard/window_dump.xml")
        raw = subprocess.run(
            [adb._adb(), "exec-out", "cat", "/sdcard/window_dump.xml"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout
        try:
            return ET.fromstring(raw)
        except ET.ParseError:
            return None

    @staticmethod
    def _bounds_center(node: "ET.Element") -> tuple[int, int] | None:
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds", ""))
        if not m:
            return None
        left, top, right, bottom = (int(g) for g in m.groups())
        return (left + right) // 2, (top + bottom) // 2

    def _find_node_by_resource_id(self, resource_id: str) -> tuple[int, int] | None:
        """Center (x, y) of the first node with `resource_id`, or None."""
        root = self._dump_ui()
        if root is None:
            return None
        for node in root.iter("node"):
            if node.attrib.get("resource-id") == resource_id:
                return self._bounds_center(node)
        return None

    # ── network gating ──────────────────────────────────────────────────────
    def _device_online(self) -> bool:
        """True iff the *device* can reach the network.

        Probes on-device (`ping` from the emulator) — a host `urllib` check
        would test the Mac's connectivity, not the emulator's, and so reports
        "online" even after the device is in airplane mode. toybox `ping`
        prints a bogus RTT on the emulator (clock quirk) but the rc and the
        "0% packet loss" / "1 received" markers are reliable.
        """
        rc, out, _ = adb.shell_check("ping -c 1 -W 2 8.8.8.8", timeout=8.0)
        # rc is 0 only when a reply arrives. The "1 received" marker is a
        # second guard; avoid "0% packet loss" — it's a substring of the
        # offline "100% packet loss" line.
        return rc == 0 and "1 received" in out

    def go_offline(self) -> None:
        # Airplane mode alone propagates too slowly / unreliably on emulator
        # images: the sync used to fire while the radio was still up and read a
        # cached `UpToDate` (the `sync.zones_offline` flake). Cut wifi + data
        # explicitly too, then *verify* the device is genuinely unreachable
        # before returning so the offline assertion isn't racing the radio.
        rc, _, err = adb.shell_check("cmd connectivity airplane-mode enable")
        if rc != 0:
            raise RuntimeError(f"failed to enable airplane mode: {err.strip()}")
        adb.set_wifi_enabled(False)
        adb.set_data_enabled(False)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if not self._device_online():
                return
            time.sleep(0.5)
        raise RuntimeError(
            "device still reachable after airplane-mode + wifi/data disable — "
            "offline assertion would be invalid"
        )

    def go_online(self) -> None:
        rc, _, err = adb.shell_check("cmd connectivity airplane-mode disable")
        if rc != 0:
            raise RuntimeError(f"failed to disable airplane mode: {err.strip()}")
        adb.set_wifi_enabled(True)
        adb.set_data_enabled(True)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if self._device_online():
                return
            time.sleep(0.5)
        raise RuntimeError("device did not regain connectivity after going online")

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
