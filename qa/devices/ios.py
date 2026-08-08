# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""IosDevice — xcrun simctl + the in-app loopback HTTP debug server.

Used when --platform ios. Requires:
  - macOS host
  - a booted iOS Simulator (`xcrun simctl list devices booted`)
  - the SrednaBG Debug build installed in that simulator

GPS, install, screenshots, app lifecycle: `xcrun simctl`. Settings / sync /
mute / network gating: HTTP GET to `127.0.0.1:47823/<action>` against the
Debug build's `DebugControlServer` (the iOS Simulator shares the host's
loopback, so no port forwarding is needed).

Why HTTP instead of `simctl openurl srednabg-debug://…`:  iOS pops an
"Open in <App>" confirmation dialog on every `simctl openurl` dispatch
for custom URL schemes, which makes automated runs unusable.

GPS injection has two modes:
  1. `geo_play(plan)` — `simctl location start --speed=… --interval=…` with
     the waypoint list on stdin. Used for steady-cruise scenarios.
  2. `geo_fix(lng, lat)` — `simctl location set` per point. Slower, used by
     mid-route mutation scenarios (gps_dropout, u_turn, wrong_direction,
     vehicle_swap). Cadence is the caller's problem; in practice this is
     driven from `qa.drive.pump()` which sleeps to the next deadline.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from qa.device import (
    Device,
    MAP_STYLE_FILES,
    MAP_STYLE_PLACEHOLDERS,
    MapIntegrityResult,
)

BUNDLE_ID = "com.demosten.srednabg"
DEBUG_SERVER_HOST = "127.0.0.1"
DEBUG_SERVER_PORT = 47823
PROD_VERSION_URL = "https://srednabg.com/api/version"


def _xcrun() -> str:
    p = shutil.which("xcrun")
    if not p:
        raise RuntimeError("xcrun not on PATH; install Xcode command-line tools")
    return p


def _run(args: list[str], *, timeout: float = 30.0, check: bool = True,
         input_text: Optional[str] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_xcrun(), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        input=input_text,
    )


def _booted_udids() -> list[str]:
    """UDIDs of every booted simulator, in `simctl` listing order."""
    p = _run(["simctl", "list", "devices", "booted"], check=False)
    if p.returncode != 0:
        return []
    # Lines look like: "    iPhone 15 (UDID) (Booted)"
    return [
        m.group(1)
        for ln in p.stdout.splitlines()
        if (m := re.search(r"\(([0-9A-Fa-f-]{36})\)\s+\(Booted\)", ln))
    ]


def _booted_udid() -> Optional[str]:
    """The simulator to test against, or None if none is booted.

    Prefers a booted simulator that actually has the app installed. Booting
    several runtimes at once is an everyday state (Simulator.app keeps them
    around), and taking the first one listed picked a device with no SrednaBG
    on it — every scenario then timed out waiting for log lines that were
    never going to be emitted. Falls back to the first booted device so the
    "not installed anywhere" case still fails with the harness's own clear
    message rather than here.
    """
    booted = _booted_udids()
    for udid in booted:
        p = _run(["simctl", "get_app_container", udid, BUNDLE_ID], check=False)
        if p.returncode == 0:
            return udid
    return booted[0] if booted else None


class IosDevice(Device):
    def __init__(self, *, udid: Optional[str] = None):
        self._udid: Optional[str] = udid

    @property
    def platform(self) -> str:
        return "ios"

    @property
    def udid(self) -> Optional[str]:
        """The resolved simulator UDID, or None before `require_device()`.

        `IosLogObserver` reads this so the log stream addresses the same
        simulator as the control channel instead of the ambiguous `booted`.
        """
        return self._udid

    @property
    def package_id(self) -> str:
        return BUNDLE_ID

    # ── lifecycle ───────────────────────────────────────────────────────────
    def require_device(self) -> str:
        if self._udid:
            return self._udid
        udid = _booted_udid()
        if not udid:
            raise RuntimeError(
                "no booted iOS simulator. Boot one with `xcrun simctl boot <udid>` "
                "or open Simulator.app and run the iOS scheme once."
            )
        self._udid = udid
        return udid

    def _device(self) -> str:
        return self._udid or "booted"

    def package_installed(self) -> bool:
        p = _run(["simctl", "get_app_container", self._device(), BUNDLE_ID],
                 check=False)
        return p.returncode == 0

    def install_app(self, path: Path) -> None:
        _run(["simctl", "install", self._device(), str(path)], timeout=180.0)

    def force_stop(self) -> None:
        _run(["simctl", "terminate", self._device(), BUNDLE_ID], check=False)

    def start_main(self) -> None:
        _run(["simctl", "launch", self._device(), BUNDLE_ID], timeout=30.0)

    def start_tracking_service(self) -> None:
        # iOS has no foreground service abstraction; tracking is started
        # by the user (or by the debug HTTP surface below).
        self._debug_get("/tracking", {"action": "start"})

    def app_running(self) -> bool:
        p = _run(["simctl", "spawn", self._device(), "launchctl", "list"],
                 check=False)
        if p.returncode != 0:
            return False
        return BUNDLE_ID in p.stdout

    def grant_runtime_permissions(self) -> None:
        # `location-always` is required: `ZoneTrackingService.start()`
        # refuses to begin tracking unless authorization is `.always`
        # (When-In-Use silently dies on screen lock). simctl grants
        # synthesize the TCC entry that CoreLocation reads — no prompt.
        _run(["simctl", "privacy", self._device(), "grant", "location-always", BUNDLE_ID],
             check=False)
        # Launch the app so the DebugControlServer binds before the first
        # /mute or /setting call. Idempotent — `simctl launch` returns
        # immediately if the app is already running.
        _run(["simctl", "launch", self._device(), BUNDLE_ID], check=False, timeout=30.0)
        self.ping_debug_server()

    def mute_audio(self) -> None:
        # No OS-level mute toggle on the simulator. Route through the app's
        # debug surface to drop AVSpeechSynthesizer calls while still
        # emitting `speak:` log lines so the parser self-test passes.
        self._debug_get("/mute", {"on": "1"})

    # ── location injection ──────────────────────────────────────────────────
    def geo_fix(self, lng: float, lat: float) -> None:
        # `simctl location set <device> <lat>,<lng>` — note: lat,lng order
        # (opposite of `adb emu geo fix`).
        _run(["simctl", "location", self._device(), "set",
              f"{lat:.7f},{lng:.7f}"], timeout=5.0)

    def feed_point(self, lat: float, lng: float, speed_ms: float,
                   bearing: float | None = None,
                   time_ms: int | None = None,
                   accuracy_m: float | None = None) -> None:
        # `accuracy_m` is accepted for API parity but ignored: iOS has no
        # MAX_ACCURACY_M gate (CoreLocation pre-filters), and the scenario
        # that uses it (noisy_fix_rejected) is Android-only.
        del accuracy_m
        # `time_ms` (epoch ms) is forwarded to /inject, which stamps the
        # injected CLLocation with it — same semantics as Android's
        # FEED_POINT `time_ms` extra, so compressed drives present the
        # encoded cadence to the speed pipeline on both platforms.
        params = {
            "lat": f"{lat:.7f}",
            "lng": f"{lng:.7f}",
            "speed": f"{speed_ms:.3f}",
        }
        if bearing is not None:
            params["bearing"] = f"{bearing:.2f}"
        if time_ms is not None:
            params["time_ms"] = str(time_ms)
        self._debug_get("/inject", params, retries=2)

    # ── debug surface (loopback HTTP) ──────────────────────────────────────
    def _debug_get(self, path: str, params: Optional[dict[str, str]] = None,
                   *, timeout: float = 10.0, retries: int = 0,
                   retry_delay_s: float = 0.3) -> str:
        """Synchronous GET to the in-app DebugControlServer. Raises if the
        request fails (server not running, wrong build, etc.).

        `retries` extra attempts are made on a transient `URLError` (a busy
        server during a fast pump), sleeping `retry_delay_s` between them, then
        the last error is re-raised. Default 0 leaves `ping_debug_server`'s own
        retry loop as the single waiter."""
        url = f"http://{DEBUG_SERVER_HOST}:{DEBUG_SERVER_PORT}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(url, timeout=timeout) as r:
                    return r.read().decode("utf-8", errors="replace")
            except urllib.error.URLError:
                if attempt >= retries:
                    raise
                attempt += 1
                time.sleep(retry_delay_s)

    def ping_debug_server(self, *, retries: int = 20, delay_s: float = 0.5) -> None:
        """Wait until the in-app debug server answers /ping. Called by
        `require_device()` so missing/unbuilt Debug builds surface fast."""
        last_err: Optional[Exception] = None
        for _ in range(retries):
            try:
                self._debug_get("/ping", timeout=1.0)
                return
            except Exception as e:
                last_err = e
                time.sleep(delay_s)
        raise RuntimeError(
            f"DebugControlServer at {DEBUG_SERVER_HOST}:{DEBUG_SERVER_PORT} "
            f"unreachable — is the Debug build installed and launched? "
            f"last error: {last_err}"
        )

    def set_setting(self, key: str, value: str) -> None:
        self._debug_get("/setting", {"key": key, "value": value}, retries=2)

    def set_zoom_override(self, zoom: float | None) -> None:
        self.set_setting("map_zoom_override", "" if zoom is None else f"{zoom}")

    def select_tab(self, name: str) -> None:
        """Switch the RootView's TabView selection over HTTP.

        Replaces the cue/ack handshake with mobile-mcp for iOS — the
        Simulator has no `simctl`-level synthetic-tap path, so without
        this the screenshot harness can't run standalone. Backed by
        `DebugActionRouter.swift`'s `/tab` case which posts the
        `DebugTabName.selectionNotification` observed by `RootView`.
        """
        if name not in ("home", "map", "history", "settings"):
            raise ValueError(f"unknown tab {name!r}; want home|map|history|settings")
        self._debug_get("/tab", {"which": name})

    def start_tracking(self) -> None:
        self._debug_get("/tracking", {"action": "start"})

    def stop_tracking(self) -> None:
        self._debug_get("/tracking", {"action": "stop"})

    def force_sync_zones(self) -> None:
        self._debug_get("/sync", {"action": "zones"})

    def force_sync_map(self) -> None:
        self._debug_get("/sync", {"action": "map"})

    def dump_history(self) -> None:
        # The DebugActionRouter emits the `DUMP_HISTORY …` line on the
        # `DebugSettings` category; `am broadcast`'s blocking-until-logged
        # behavior on Android is matched here by the synchronous HTTP round
        # trip returning only after the handler has emitted.
        self._debug_get("/history", {"action": "dump"}, retries=2)

    def seed_history(self, count: int) -> None:
        self._debug_get("/history", {"action": "seed", "count": str(count)},
                        retries=2)

    def ensure_history_list(self) -> None:
        # No-op by construction: every shot flips `app_language`, which rebuilds
        # the language-keyed `RootTabs` — the NavigationStack comes back at its
        # root and `debugDetailRecord` resets to nil.
        return

    def open_history_detail(self, select: str = "newest") -> None:
        self._debug_get("/history", {"action": "open", "select": select}, retries=2)

    # ── network gating ──────────────────────────────────────────────────────
    def go_offline(self) -> None:
        # `simctl status_bar` flips the carrier glyph but doesn't gate the
        # network. The debug build short-circuits sync requests to Failed
        # while QAFlags.networkOffline is set.
        self._debug_get("/network", {"offline": "1"})
        time.sleep(0.5)

    def go_online(self) -> None:
        self._debug_get("/network", {"offline": "0"})
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
        _run(["simctl", "ui", self._device(), "appearance", mode], timeout=5.0)

    def override_status_bar(self) -> None:
        _run([
            "simctl", "status_bar", self._device(), "override",
            "--time", "9:41",
            "--dataNetwork", "wifi",
            "--wifiMode", "active", "--wifiBars", "3",
            "--cellularMode", "active", "--cellularBars", "4",
            "--batteryState", "charged", "--batteryLevel", "100",
        ], timeout=5.0)

    def clear_status_bar_override(self) -> None:
        _run(["simctl", "status_bar", self._device(), "clear"], timeout=5.0,
             check=False)

    # ── inspection ──────────────────────────────────────────────────────────
    def screencap(self, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["simctl", "io", self._device(), "screenshot", str(dest)], timeout=15.0)
        return dest

    def crash_buffer(self) -> str:
        # iOS app crashes land in ~/Library/Logs/DiagnosticReports/ on the
        # host (simctl shares the host filesystem). Aggregate any *.ips
        # whose name contains the bundle id. This is a snapshot of
        # everything-since-boot; the runner clears between scenarios via
        # `clear_crash_buffer()` (records the watermark).
        try:
            home = Path.home() / "Library/Logs/DiagnosticReports"
            if not home.exists():
                return ""
            cutoff = getattr(self, "_crash_watermark", 0.0)
            new_chunks: list[str] = []
            for p in sorted(home.glob("*")):
                if BUNDLE_ID.split(".")[-1] not in p.name:
                    continue
                try:
                    if p.stat().st_mtime <= cutoff:
                        continue
                    new_chunks.append(p.read_text(errors="ignore"))
                except Exception:
                    pass
            return "\n\n".join(new_chunks)
        except Exception:
            return ""

    def clear_crash_buffer(self) -> None:
        # Don't delete user-owned DiagnosticReports; just bump the
        # watermark so subsequent `crash_buffer()` only sees files newer
        # than this moment.
        self._crash_watermark = time.time()

    def check_map_integrity(self) -> MapIntegrityResult:
        # Locate the app's data container, then inspect the bundled map.
        p = _run(["simctl", "get_app_container", self._device(), BUNDLE_ID, "data"],
                 check=False)
        if p.returncode != 0:
            return MapIntegrityResult(False, False, [], 0)
        container = Path(p.stdout.strip())
        # The app roots its managed data under an `SrednaBG/` subdir of
        # Application Support — `OfflineMapInstaller(rootDir:)` is handed
        # `ZoneStore.defaultURL().deletingLastPathComponent()`, i.e.
        # `…/Application Support/SrednaBG`, and installs the bundle into
        # `<root>/map`. Mirror that exact layout.
        map_dir = container / "Library" / "Application Support" / "SrednaBG" / "map"
        mbtiles = map_dir / "bulgaria.mbtiles"

        # The bundle ships a light + dark style; both must be installed.
        # `style_present` is the AND across them. (Placeholders are rewritten
        # in memory at load time, not on disk — see `placeholders_expected`.)
        styles_present = True
        placeholders: list[str] = []
        for style_name in MAP_STYLE_FILES:
            style = map_dir / style_name
            if not style.exists():
                styles_present = False
                continue
            try:
                content = style.read_text(errors="ignore")
                for ph in MAP_STYLE_PLACEHOLDERS:
                    if ph in content and ph not in placeholders:
                        placeholders.append(ph)
            except Exception:
                pass

        size = mbtiles.stat().st_size if mbtiles.exists() else 0
        return MapIntegrityResult(
            style_present=styles_present,
            mbtiles_present=mbtiles.exists(),
            placeholders_remaining=placeholders,
            mbtiles_size_bytes=size,
            # iOS rewrites the style placeholders in memory at load time, so
            # the on-disk template legitimately keeps them — see OfflineMapInstaller.
            placeholders_expected=True,
        )

    # ── iOS-specific helper: GPX route playback ────────────────────────────
    def geo_play(self, *, points: list[tuple[float, float]],
                 speed_mps: float, interval_s: float = 1.0) -> None:
        """Drive `simctl location start` with a waypoint list. Blocks for
        the expected duration; final waypoint stays pinned on completion."""
        payload = "".join(f"{lat:.7f},{lng:.7f}\n" for lat, lng in points)
        cmd = ["simctl", "location", self._device(), "start",
               f"--speed={speed_mps:.3f}", f"--interval={interval_s}", "-"]
        _run(cmd, input_text=payload, timeout=10.0)
