#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""App Store / Play Store screenshot harness.

Drives a booted Android emulator or iOS Simulator through a fixed shot
list (qa/screenshots/shots.yaml), in each configured language, and saves
PNGs to web/screenshots/<os>/<NN>-<os>-<theme>-<lang>.png.

Usage (from repo root):

    python qa/srednabg_screenshots.py android                # full set, light theme
    python qa/srednabg_screenshots.py ios 4                  # one shot by NN, both langs
    python qa/srednabg_screenshots.py android map-north-green        # by name
    python qa/srednabg_screenshots.py android 3 bg                   # single PNG
    python qa/srednabg_screenshots.py android --theme dark           # dark device theme

The orchestrator owns build/install (when invoked via the Claude skill),
settings, GPS injection, and screencap. Tab switches happen out-of-band
via the Claude session driving mobile-mcp — the orchestrator writes a
cue file and polls for an ack file. When run standalone (no Claude
session), the orchestrator falls back to coordinate-based adb taps for
Android only; on iOS the cue files stay unacked and the run errors out.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from qa._preflight import require  # noqa: E402

require("yaml")

from qa import device as device_mod  # noqa: E402
from qa.screenshots import loader as shots_loader  # noqa: E402
from qa.screenshots import sequencer  # noqa: E402

REPO_ROOT = _HERE.parent
WEB_SCREENSHOTS = REPO_ROOT / "web" / "screenshots"
REPORTS_ROOT = _HERE / "reports"

# Ack file polling: how long the skill has to respond to a tap_tab cue.
CUE_ACK_TIMEOUT_S = 60.0
CUE_POLL_INTERVAL_S = 0.2


# ─────────────────────────── Cue handshake ───────────────────────────


class CueChannel:
    """One-directional cue queue with file-based ack handshake.

    Orchestrator writes `cue-<seq>.json` under `signal/`; Claude session
    or fallback writes `ack-<seq>.json` once the action is done.
    """

    def __init__(self, signal_dir: Path):
        self.dir = signal_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seq = 0

    def emit(self, kind: str, args: dict) -> int:
        self.seq += 1
        payload = {"seq": self.seq, "kind": kind, **args,
                   "ts": datetime.now(timezone.utc).isoformat()}
        cue_path = self.dir / f"cue-{self.seq:04d}.json"
        cue_path.write_text(json.dumps(payload), encoding="utf-8")
        return self.seq

    def wait_ack(self, seq: int, *, timeout_s: float = CUE_ACK_TIMEOUT_S) -> None:
        ack_path = self.dir / f"ack-{seq:04d}.json"
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if ack_path.exists():
                return
            time.sleep(CUE_POLL_INTERVAL_S)
        raise TimeoutError(
            f"no ack for cue {seq} after {timeout_s}s. The /screenshot-app skill "
            f"should be tailing {self.dir} and writing ack-{seq:04d}.json."
        )


# ─────────────────────────── Tab navigation ───────────────────────────


# Fallback bottom-nav coordinates for headless Android runs (no Claude session).
# Pixel 8a 1080×2400 portrait — same numbers the existing smoke_walk uses.
ANDROID_TAB_COORDS = {
    "home": (180, 2253),
    "map": (540, 2253),
    "settings": (900, 2253),
}


def navigate_tab(tab: str, channel: CueChannel, *, allow_adb_fallback: bool) -> None:
    """Switch to one of the bottom tabs.

    iOS path: drive the RootView's TabView selection over HTTP via the
    in-app debug listener's `/tab` endpoint (no mobile-mcp needed). A cue
    file is still emitted for log/debugging continuity, immediately self-
    acked so the skill (when present) sees a closed handshake.

    Android paths:
      - Preferred: emit a cue and let the Claude session do an
        accessibility-id tap via mobile-mcp.
      - `--allow-adb-fallback` (headless): tap by coordinate immediately.
    """
    accessibility_id = f"tab-{tab}"
    seq = channel.emit("tap_tab", {
        "tab": tab,
        "accessibility_id": accessibility_id,
    })
    d = device_mod.current()

    # iOS path: HTTP-drive the TabView selection. Self-ack so any tailing
    # skill sees a closed handshake without contending for the tap.
    if d.platform == "ios":
        d.select_tab(tab)
        (channel.dir / f"ack-{seq:04d}.json").write_text(
            json.dumps({"by": "ios-http", "tab": tab}), encoding="utf-8")
        return

    # Android headless: skip the wait, tap immediately, ack ourselves.
    if d.platform == "android" and allow_adb_fallback:
        from qa import adb
        x, y = ANDROID_TAB_COORDS[tab]
        adb.shell(f"input tap {x} {y}")
        (channel.dir / f"ack-{seq:04d}.json").write_text(
            json.dumps({"by": "adb-fallback", "tab": tab}), encoding="utf-8")
        return

    # Android skill-driven path: poll for an ack from the Claude session.
    # 30s budget — each cue costs the Claude session one model turn
    # (notification → mobile-mcp tap → ack file write). Model-turn latency
    # is typically 4-8s; 30s leaves headroom for slow tool calls without
    # tying up the orchestrator forever if the skill stops responding.
    try:
        channel.wait_ack(seq, timeout_s=30.0)
        return
    except TimeoutError:
        pass

    raise TimeoutError(
        f"tab switch to {tab!r} unacked (cue {seq}); no fallback available")


# ─────────────────────────── Pre-flight & teardown ───────────────────────────


def preflight(device, *, theme: str = "light", mute: bool = True) -> None:
    """Cosmetic + lifecycle setup that runs once before the shot loop."""
    device.require_device()
    device.grant_runtime_permissions()
    if mute:
        device.mute_audio()
    device.set_system_appearance(theme)
    device.override_status_bar()
    device.force_stop()
    device.start_main()
    # Give the app a moment to bind its debug surface.
    time.sleep(3.0)
    device.start_tracking()


def teardown(device) -> None:
    try:
        device.stop_tracking()
    except Exception:
        pass
    try:
        device.clear_status_bar_override()
    except Exception:
        pass


# ─────────────────────────── Shot execution ───────────────────────────


def apply_shot_settings(device, shot: shots_loader.Shot, run_theme: str = "light") -> None:
    if shot.map_heading_up is not None:
        device.set_setting("map_heading_up", "true" if shot.map_heading_up else "false")
    # Resolve the in-app map theme. Shots that lock a specific theme (e.g.
    # map-heading-yellow-dark) take precedence; shots that leave it unset
    # mirror the run's --theme so OS-dark captures actually get a dark map.
    map_theme = shot.map_theme_mode if shot.map_theme_mode is not None else run_theme
    if shot.tab == "map" or shot.map_theme_mode is not None:
        # Android DataStore stores the enum NAME (uppercase).
        device.set_setting("map_theme_mode", map_theme.upper())
    device.set_zoom_override(shot.map_zoom_override)
    # Force a story-friendly "Max now" — the live computation often lands at
    # the 250 cap (huge headroom) or near 0 (already over limit). The chip /
    # InZoneCard render this override instead when set; the underlying speed
    # math is unchanged.
    device.set_setting(
        "debug_max_speed_override",
        "" if shot.max_now_override is None else str(shot.max_now_override),
    )


def restore_after_shot(device, shot: shots_loader.Shot) -> None:
    if shot.map_zoom_override is not None:
        device.set_zoom_override(None)
    if shot.max_now_override is not None:
        device.set_setting("debug_max_speed_override", "")
    # Heading/theme persist across shots intentionally — they're usually
    # toggled per-group and re-set explicitly by the next shot's recipe.


def wait_locale_applied(device) -> None:
    """Short settle after app_language flip. Android recreates MainActivity."""
    time.sleep(2.0 if device.platform == "android" else 0.5)


def drive_band_for_shot(seq: sequencer.ZoneSequencer, shot: shots_loader.Shot) -> None:
    """Drive the GPS sequence required by `shot.band`.

    Every in-zone shot is driven from a fresh tracking session: we
    stop+restart tracking before driving so the on-device `ZoneDetector`
    AND `SpeedInference` (GpsPointBuilder) both reset cleanly. The
    earlier "brief outside burst" approach injected a GPS fix at Sofia
    immediately before fixes at the zone start, producing a hundreds-of-km
    position jump between consecutive fixes. iOS `SpeedInference` (mirroring
    AAOS's `LocationTrackingService.kt`) clamps the derived speed at
    250 km/h on that jump and `max()`es it with the reported value, which
    then dragged the in-zone running average above the limit and turned
    every "green" shot red.

    Each in-zone shot owns its own sequence — nothing is carried across shots.
    """
    band = shot.band
    if not shot.tracking_active:
        # Cold-start marketing shots (home idle, map overview): tracking
        # must be off so the Start button / empty user-arrow state shows.
        # Loader already enforces band==none for this combination.
        device_mod.current().stop_tracking()
        time.sleep(0.5)
        return None
    if band == "none":
        return None
    if band == "outside":
        assert shot.cur_speed_kmh is not None
        sequencer.drive_outside(cur_speed_kmh=shot.cur_speed_kmh, duration_s=6.0)
        return None
    if band in ("green", "yellow", "red"):
        # Restart tracking to fully reset detector + GpsPointBuilder
        # (SpeedInference, BearingFallback, GpsFilter). On iOS this routes
        # through CLLocationTracker.stop() which calls `builder.reset()`;
        # on Android the LocationTrackingService rebuild has the same
        # effect.
        d = device_mod.current()
        d.stop_tracking()
        time.sleep(0.5)
        d.start_tracking()
        time.sleep(1.5)
        sequencer._reset_pacing()  # noqa: SLF001 — module-private by intent
        if band == "red":
            # RED needs running avg > limit. The detector integrates the
            # in-zone history, so we lift the avg by driving the preamble
            # already above the limit — a short tail at +35 then crosses.
            walker = seq.drive_into_zone(
                preamble_speed_kmh=seq.zone.speed_limit_kmh + 25.0,
                preamble_s=10.0,
            )
        else:
            walker = seq.drive_into_zone()
        seq.drive_band_tail(walker, band)
        return
    raise ValueError(f"unhandled band: {band!r}")


def settle_for_screenshot() -> None:
    time.sleep(1.0)


# ─────────────────────────── Main ───────────────────────────


@dataclass(frozen=True)
class CliArgs:
    platform: str
    shot_selector: Optional[str]  # None | "NN" | "name"
    lang: Optional[str]
    theme: str  # "light" | "dark"
    allow_adb_fallback: bool


def parse_args(argv: list[str]) -> CliArgs:
    p = argparse.ArgumentParser(
        description="SrednaBG App Store / Play Store screenshot harness")
    p.add_argument("platform", choices=("android", "ios"))
    p.add_argument("shot", nargs="?", default=None,
                   help="shot NN (e.g. 3) or name (e.g. map-north-green); "
                        "omit to run every shot")
    p.add_argument("lang", nargs="?", default=None, choices=("en", "bg"),
                   help="single language; omit to run both")
    p.add_argument("--lang", dest="lang_flag", default=None,
                   choices=("en", "bg"),
                   help="single language as a flag; useful when you want "
                        "all shots in one language without picking a shot")
    p.add_argument("--theme", default="light", choices=("light", "dark"),
                   help="system/device theme to force before capture. "
                        "Embedded in the output filename (default: light).")
    p.add_argument("--allow-adb-fallback", action="store_true",
                   help="(Android only, headless) tap nav by coordinate when "
                        "the Claude session doesn't ack tap_tab cues. Useful "
                        "for unattended testing of the orchestrator.")
    ns = p.parse_args(argv)
    return CliArgs(
        platform=ns.platform,
        shot_selector=ns.shot,
        lang=ns.lang_flag or ns.lang,
        theme=ns.theme,
        allow_adb_fallback=ns.allow_adb_fallback,
    )


def resolve_shots(cfg: shots_loader.ShotConfig,
                  selector: Optional[str]) -> list[shots_loader.Shot]:
    if selector is None:
        return list(cfg.shots)
    if selector.isdigit():
        return [cfg.by_index(int(selector))]
    return [cfg.by_name(selector)]


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    cfg = shots_loader.load()
    shots = resolve_shots(cfg, args.shot_selector)
    langs = [args.lang] if args.lang else list(cfg.languages)

    device = device_mod.make(args.platform)
    device_mod.set_current(device)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = REPORTS_ROOT / f"screenshots-{args.platform}-{ts}"
    report_dir.mkdir(parents=True, exist_ok=True)
    signal_dir = report_dir / "signal"
    channel = CueChannel(signal_dir)
    print(f"signal dir: {signal_dir}")

    out_root = WEB_SCREENSHOTS / args.platform
    out_root.mkdir(parents=True, exist_ok=True)

    zone = sequencer.load_zone(cfg.zone_id)
    seq = sequencer.ZoneSequencer(zone=zone)

    preflight(device, theme=args.theme)
    produced: list[Path] = []

    try:
        for shot in shots:
            for lang in langs:
                print(f"\n=== shot {shot.nn:02d} ({shot.name!r}) — "
                      f"{args.theme}/{lang} ===")
                device.set_setting("app_language", lang)
                wait_locale_applied(device)
                apply_shot_settings(device, shot, run_theme=args.theme)
                navigate_tab(shot.tab, channel,
                             allow_adb_fallback=args.allow_adb_fallback)
                time.sleep(0.5)  # UI settle
                drive_band_for_shot(seq, shot)
                settle_for_screenshot()
                dest = out_root / (
                    f"{shot.nn:02d}-{args.platform}-{args.theme}-{lang}.png"
                )
                device.screencap(dest)
                produced.append(dest)
                print(f"  → {dest}")
                restore_after_shot(device, shot)
    finally:
        teardown(device)

    print(f"\nproduced {len(produced)} screenshot(s):")
    for p in produced:
        sz = p.stat().st_size if p.exists() else 0
        print(f"  {p}  ({sz} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
