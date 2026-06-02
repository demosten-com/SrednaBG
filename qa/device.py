# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Platform-agnostic Device facade used by the runner, scenarios, and assertions.

The harness was originally adb-only. With the iOS Simulator backend, every
call that used to go through `qa.adb` now flows through `current().foo()`,
and the concrete implementation lives in `qa/devices/android.py` or
`qa/devices/ios.py`.

This module is intentionally tiny: ABC + a single-instance singleton.
Selection happens once at startup in `qa/srednabg_qa.py` (`--platform`),
or implicitly through `select_default()` which prefers a booted iOS
simulator on macOS over an adb device when both are present.
"""

from __future__ import annotations

import abc
import sys
from pathlib import Path
from typing import Optional


class Device(abc.ABC):
    """Operations the harness needs to drive an app under test.

    Implementations:
      - qa.devices.android.AndroidDevice — wraps adb.
      - qa.devices.ios.IosDevice — wraps xcrun simctl + the iOS app's
        srednabg-debug:// URL scheme.

    Methods are grouped by responsibility. The runner only ever talks to
    this protocol; scenario files may still talk to the underlying
    Android-specific helpers in `qa.adb` when an iOS analogue doesn't
    exist (cold_start_spike, _helpers, bulk_loader) — those scenarios are
    skipped under `--platform ios`.
    """

    # ── identity ────────────────────────────────────────────────────────────
    @property
    @abc.abstractmethod
    def platform(self) -> str: ...

    @property
    @abc.abstractmethod
    def package_id(self) -> str: ...

    # ── lifecycle ───────────────────────────────────────────────────────────
    @abc.abstractmethod
    def require_device(self) -> str: ...

    @abc.abstractmethod
    def package_installed(self) -> bool: ...

    @abc.abstractmethod
    def install_app(self, path: Path) -> None: ...

    @abc.abstractmethod
    def force_stop(self) -> None: ...

    @abc.abstractmethod
    def start_main(self) -> None: ...

    @abc.abstractmethod
    def start_tracking_service(self) -> None: ...

    @abc.abstractmethod
    def app_running(self) -> bool: ...

    @abc.abstractmethod
    def grant_runtime_permissions(self) -> None: ...

    @abc.abstractmethod
    def mute_audio(self) -> None: ...

    # ── location injection ──────────────────────────────────────────────────
    @abc.abstractmethod
    def geo_fix(self, lng: float, lat: float) -> None:
        """Push a single mock GPS point. Cadence is the caller's problem."""

    @abc.abstractmethod
    def feed_point(self, lat: float, lng: float, speed_ms: float,
                   bearing: Optional[float] = None) -> None:
        """Inject a fix with speed and bearing through the app's debug back-channel.

        Unlike `geo_fix`, this goes through the in-app debug surface
        (Android FEED_POINT broadcast / iOS /inject HTTP endpoint), which
        lets the screenshot harness drive precise speed values into the
        zone state machine without waiting for FLP to synthesize speed
        from successive positions. Required for deterministic Green /
        Yellow / Red band selection in the screenshot orchestrator.
        """

    # ── debug surface ───────────────────────────────────────────────────────
    @abc.abstractmethod
    def set_setting(self, key: str, value: str) -> None:
        """Apply one app setting via the platform's debug control surface."""

    @abc.abstractmethod
    def set_zoom_override(self, zoom: Optional[float]) -> None:
        """Pin the map view at a specific zoom level, or clear with None.

        Screenshot-only. When set, the map skips its auto fit-bounds and
        sticks at the given zoom for deterministic framing.
        """

    @abc.abstractmethod
    def start_tracking(self) -> None: ...

    @abc.abstractmethod
    def stop_tracking(self) -> None: ...

    @abc.abstractmethod
    def force_sync_zones(self) -> None: ...

    @abc.abstractmethod
    def force_sync_map(self) -> None: ...

    # ── network gating ──────────────────────────────────────────────────────
    @abc.abstractmethod
    def go_offline(self) -> None: ...

    @abc.abstractmethod
    def go_online(self) -> None: ...

    # ── cosmetic chrome (screenshot harness) ────────────────────────────────
    @abc.abstractmethod
    def set_system_appearance(self, mode: str) -> None:
        """Force the device into 'light' or 'dark' system theme."""

    @abc.abstractmethod
    def override_status_bar(self) -> None:
        """Lock the status bar to a clean App Store look (time 9:41, full
        battery, full wifi, no notifications). Idempotent."""

    @abc.abstractmethod
    def clear_status_bar_override(self) -> None:
        """Restore the system-driven status bar."""

    # ── inspection ──────────────────────────────────────────────────────────
    @abc.abstractmethod
    def screencap(self, dest: Path) -> Path: ...

    @abc.abstractmethod
    def crash_buffer(self) -> str: ...

    @abc.abstractmethod
    def clear_crash_buffer(self) -> None: ...

    @abc.abstractmethod
    def check_map_integrity(self) -> "MapIntegrityResult":
        """Structured map-bundle integrity result. Per-platform impl."""


# Re-exported here so qa.sync's data class stays its canonical home but
# Device's abstract method can reference it without an import cycle.
from dataclasses import dataclass


@dataclass(frozen=True)
class MapIntegrityResult:
    style_present: bool  # True only when ALL required style files are installed
    mbtiles_present: bool
    placeholders_remaining: list[str]
    mbtiles_size_bytes: int
    # iOS keeps the on-disk styles as raw `{…_URI}` templates and rewrites them
    # in memory at load time (StyleRewriter) — the sandbox container UUID
    # changes across reinstall / OS restore, so absolute paths can't be baked
    # in. Android rewrites the style in place on disk. When this is True,
    # leftover placeholders are the expected, healthy state — not a failure.
    placeholders_expected: bool = False


# The offline map bundle ships a light + dark MapLibre style — Android's
# `MapRepository.STYLE_FILES`, iOS's `OfflineMapInstaller.Layout.styleFileNames`.
# Both must be present and fully placeholder-rewritten for the bundle to be
# healthy. Kept here so the Android + iOS device backends check the same set
# (there is no single `style.json` any more).
MAP_STYLE_FILES: tuple[str, ...] = ("style-light.json", "style-dark.json")
MAP_STYLE_PLACEHOLDERS: tuple[str, ...] = ("{MBTILES_URI}", "{GLYPHS_URI}", "{SPRITE_URI}")


# ────────────────────────────── active device ──────────────────────────────

_current: Optional[Device] = None


def current() -> Device:
    if _current is None:
        # Lazy default: pick whatever the host has booted.
        set_current(select_default())
    assert _current is not None
    return _current


def set_current(d: Device) -> None:
    global _current
    _current = d


def select_default() -> Device:
    """Pick the right backend based on platform + what's booted.

    On macOS with a booted simulator and no adb device, picks iOS.
    On macOS with both, picks Android (preserves legacy behavior).
    Off macOS, always Android.
    """
    if sys.platform == "darwin":
        try:
            from qa.devices.android import AndroidDevice
            android = AndroidDevice()
            android.require_device()
            return android
        except Exception:
            pass
        try:
            from qa.devices.ios import IosDevice
            ios = IosDevice()
            ios.require_device()
            return ios
        except Exception:
            pass
        raise RuntimeError(
            "no device available — boot an Android emulator (adb) or iOS simulator "
            "(xcrun simctl boot) first"
        )
    from qa.devices.android import AndroidDevice
    return AndroidDevice()


def make(platform: str) -> Device:
    """Explicit factory used by --platform <name>."""
    if platform == "android":
        from qa.devices.android import AndroidDevice
        return AndroidDevice()
    if platform == "ios":
        if sys.platform != "darwin":
            raise RuntimeError("--platform ios requires macOS host")
        from qa.devices.ios import IosDevice
        return IosDevice()
    if platform == "auto":
        return select_default()
    raise ValueError(f"unknown platform: {platform!r}")
