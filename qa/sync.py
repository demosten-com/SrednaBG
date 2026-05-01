# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Sync test helpers — wraps DebugSyncReceiver + map-bundle integrity check.

The harness uses three sync flows:

1. Happy path: broadcast SYNC_X, wait for `DebugSync` log, assert
   outcome was Updated/UpToDate.
2. Failure path: kill connectivity, broadcast SYNC_X, assert Failed.
3. Map integrity: after a successful SYNC_MAP, verify on-disk style.json
   has been rewritten (no `{MBTILES_URI}` placeholders) and the
   bulgaria.mbtiles file is present + non-empty.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from . import adb
from .events import SyncResult
from .logcat import LogcatObserver

DEBUG_SYNC_RECEIVER = f"{adb.PACKAGE}/{adb.PACKAGE}.app.debug.DebugSyncReceiver"
ACTION_SYNC_MAP = "com.demosten.srednabg.debug.SYNC_MAP"
ACTION_SYNC_ZONES = "com.demosten.srednabg.debug.SYNC_ZONES"


def force_sync_zones() -> None:
    adb.broadcast(ACTION_SYNC_ZONES, DEBUG_SYNC_RECEIVER)


def force_sync_map() -> None:
    adb.broadcast(ACTION_SYNC_MAP, DEBUG_SYNC_RECEIVER)


def wait_for_sync(obs: LogcatObserver, action_suffix: str, *, timeout_s: float = 30.0) -> SyncResult:
    """Block until a `DebugSync` log line shows the action completed.

    `action_suffix` is the short tail (`SYNC_ZONES`, `SYNC_MAP`).
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            ev = obs.queue.get(timeout=0.5)
        except Exception:
            continue
        if isinstance(ev, SyncResult) and ev.action == action_suffix:
            return ev
    raise TimeoutError(f"no DebugSync result for {action_suffix} within {timeout_s}s")


# ──────────────────────────── network toggles ────────────────────────────
#
# Both debug and release builds talk to the production host
# (https://srednabg.com), so simulating "offline" means cutting the
# emulator's connectivity, not the local backend. We toggle airplane mode
# via the radio settings broadcast — clean, deterministic, and not subject
# to the `svc wifi disable` DHCP-re-association bug on Pixel_8a / Android 14.

PROD_VERSION_URL = "https://srednabg.com/api/version"


def _set_airplane_mode(enabled: bool) -> None:
    # `cmd connectivity airplane-mode` lands on Android 12+ (API 31). The
    # Pixel_8a emulator runs Android 14, so this is always available.
    state = "enable" if enabled else "disable"
    rc, _, err = adb.shell_check(f"cmd connectivity airplane-mode {state}")
    if rc != 0:
        raise RuntimeError(f"failed to {state} airplane mode: {err.strip()}")


def go_offline() -> None:
    """Put the emulator into airplane mode so the app sees ConnectException."""
    _set_airplane_mode(True)
    time.sleep(1.5)  # let the radio drop and ConnectivityManager settle


def go_online(*, settle_timeout_s: float = 15.0) -> None:
    """Leave airplane mode and poll the prod host until /api/version responds."""
    _set_airplane_mode(False)

    import urllib.request
    deadline = time.monotonic() + settle_timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(PROD_VERSION_URL, timeout=2.0) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.5)


# ──────────────────────────── map integrity ────────────────────────────


@dataclass(frozen=True)
class MapIntegrityResult:
    style_present: bool
    mbtiles_present: bool
    placeholders_remaining: list[str]
    mbtiles_size_bytes: int


def check_map_integrity() -> MapIntegrityResult:
    """Inspect filesDir/map/ via run-as. Catches the 'synced but app
    crashes on map open' class of regressions.

    Returns a structured result; the runner converts it into pass/fail.
    """
    files_dir = f"/data/data/{adb.PACKAGE}/files/map"
    style_present = adb.file_exists_in_app(adb.PACKAGE, f"{files_dir}/style.json")
    mbtiles_present = adb.file_exists_in_app(adb.PACKAGE, f"{files_dir}/bulgaria.mbtiles")

    placeholders: list[str] = []
    if style_present:
        try:
            content = adb.run_as_read(adb.PACKAGE, f"{files_dir}/style.json")
            for ph in ("{MBTILES_URI}", "{GLYPHS_URI}", "{SPRITE_URI}"):
                if ph in content:
                    placeholders.append(ph)
        except Exception:
            pass

    size = 0
    if mbtiles_present:
        rc, out, _ = adb.shell_check(
            f"run-as {adb.PACKAGE} stat -c %s {files_dir}/bulgaria.mbtiles"
        )
        if rc == 0:
            try:
                size = int(out.strip())
            except ValueError:
                size = 0
    return MapIntegrityResult(
        style_present=style_present,
        mbtiles_present=mbtiles_present,
        placeholders_remaining=placeholders,
        mbtiles_size_bytes=size,
    )


def assert_map_integrity_ok(result: MapIntegrityResult) -> None:
    from .assertions import AssertionFailure
    problems: list[str] = []
    if not result.style_present:
        problems.append("style.json missing")
    if not result.mbtiles_present:
        problems.append("bulgaria.mbtiles missing")
    if result.placeholders_remaining:
        problems.append(f"unrewritten placeholders in style.json: {result.placeholders_remaining}")
    if result.mbtiles_present and result.mbtiles_size_bytes < 1_000_000:
        problems.append(f"bulgaria.mbtiles suspiciously small: {result.mbtiles_size_bytes} bytes")
    if problems:
        raise AssertionFailure(f"map integrity check failed: {'; '.join(problems)}")
