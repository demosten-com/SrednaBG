#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Record a Play Console "Video instructions" demo of the running-average feature.

Drives the running Android emulator through a real Bulgarian section-control
zone in real time, captures video via `adb shell screenrecord` and (optionally)
device audio via an already-configured Audio Hijack session, muxes them, and
trims to a fixed length (default 30 s).

Storyboard (wall time, defaults):
  0:00  fresh Home screen, "Start tracking" button visible
  ~0:01 tap Start tracking — button flips to Stop
  ~0:02 GPS pump begins; first fix lands at zone-entry centerline → Home swaps
        in the InZoneCard with running avg / current / limit / max-sustainable
  ~0:02 TTS announces zone entry (captured if --audio-dir is set)
  0:02 – 0:14  numbers update on Home so the viewer sees the feature work
  ~0:14 tap Map tab → ZoneMapScreen opens centred on the live GPS position
  0:14 – 0:30  map pans along the zone; InZoneChip overlay shows the same
        readouts as the Home card
  0:30  cut while still in-zone

Output: qa/out/video/srednabg-demo-<duration>s.mp4

Audio (optional):
  Pass --audio-dir <path> to mux in audio captured by an Audio Hijack session
  whose Recorder writes to that folder. The script clicks "Control > Run
  Session" at start and again at stop via AppleScript UI scripting (requires
  Accessibility permission for the calling Terminal). After the run, it picks
  the freshest audio file in the folder and muxes with the video.

Without --audio-dir the video is silent (Play Console accepts silent
walkthroughs). scrcpy is intentionally not used — it crashes immediately on
this Android 14 emulator stack.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from qa import adb  # noqa: E402
from qa import device as device_mod  # noqa: E402
from qa.devices.android import AndroidDevice  # noqa: E402
from qa.drive import parse_gpx, pump  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
ZONES_JSON = REPO_ROOT / "backend" / "data" / "zones.json"
MAKE_TEST_ROUTE = REPO_ROOT / "scrapers" / "scripts" / "make_test_route.py"
OUT_DIR = REPO_ROOT / "qa" / "out" / "video"
FIXTURES_DIR = REPO_ROOT / "qa" / "fixtures" / "gpx"

DEFAULT_ZONE = "trakiya-01-east"
DEFAULT_SPEED_KMH = 120.0
DEFAULT_DURATION_S = 30
DEFAULT_HOME_SECONDS = 12
RECORD_SAFETY_S = 5
AUDIO_EXTS = (".m4a", ".aac", ".wav", ".mp3", ".aif", ".aiff", ".caf")


def _load_route_helpers():
    """Import scrapers/scripts/make_test_route.py without installing it."""
    spec = importlib.util.spec_from_file_location("make_test_route", MAKE_TEST_ROUTE)
    if not spec or not spec.loader:
        raise RuntimeError(f"could not load {MAKE_TEST_ROUTE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_no_approach_gpx(zone_id: str, speed_kmh: float, point_count: int,
                          out_path: Path) -> int:
    """Generate a GPX whose first fix is at the zone-entry centerline point.

    Caps the point list at `point_count` fixes at 1 Hz (no approach, no exit
    overshoot). The Android `ZoneDetector` marks InZone immediately from the
    first fix when it lands inside a zone, so the demo sees the running
    average build from second zero.
    """
    mod = _load_route_helpers()
    zone = mod.load_zone(ZONES_JSON, zone_id)
    centerline = [(p[0], p[1]) for p in zone["centerline"]]
    if len(centerline) < 2:
        raise RuntimeError(f"zone {zone_id} has fewer than 2 centerline points")

    step_m = speed_kmh / 3.6  # one fix per second at 1 Hz
    pts = list(mod.resample_polyline(centerline, step_m))
    pts = pts[:point_count]
    if len(pts) < point_count:
        raise RuntimeError(
            f"zone {zone_id} centerline too short for {point_count}s @ {speed_kmh:.0f} km/h "
            f"(got {len(pts)} fixes, need {point_count})"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mod.emit_gpx(pts, 1.0, out_path, name=f"{zone_id}_demo")
    return len(pts)


def _dump_ui() -> ET.Element:
    adb.shell("uiautomator dump /sdcard/window_dump.xml")
    raw = subprocess.run(
        [shutil.which("adb"), "exec-out", "cat", "/sdcard/window_dump.xml"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    return ET.fromstring(raw)


def _find_bounds(root: ET.Element, *, text: Optional[str] = None,
                 resource_id: Optional[str] = None) -> Optional[tuple[int, int, int, int]]:
    for node in root.iter("node"):
        if text is not None and node.attrib.get("text") != text:
            continue
        if resource_id is not None and resource_id not in node.attrib.get("resource-id", ""):
            continue
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds", ""))
        if m:
            return (int(m[1]), int(m[2]), int(m[3]), int(m[4]))
    return None


def _find_and_tap(*matchers: dict, timeout_s: float = 10.0) -> tuple[int, int, int, int]:
    """Poll the UI dump until one of the matchers hits, then tap its center."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        root = _dump_ui()
        for m in matchers:
            bounds = _find_bounds(root, **m)
            if bounds:
                left, t, r, b = bounds
                adb.shell(f"input tap {(left + r) // 2} {(t + b) // 2}")
                return bounds
        time.sleep(0.5)
    raise RuntimeError(f"no UI node matched any of: {matchers}")


def _whitelist_battery_opt(pkg: str) -> None:
    """Take the app off doze whitelist so BatteryOptimizationCard doesn't show."""
    adb.shell(f"dumpsys deviceidle whitelist +{pkg}")


def _max_media_volume() -> None:
    """Bump STREAM_MUSIC to its ceiling so TTS amplitude is high in the capture."""
    for _ in range(20):
        adb.shell("input keyevent 24")  # KEYCODE_VOLUME_UP


def _toggle_audio_hijack_session() -> None:
    """Click 'Control > Run Session' in Audio Hijack to start/stop the recorder.

    The menu item is the same for both directions — clicking it while idle
    starts the session; clicking it while running stops it. Requires that the
    user has set up a session that captures qemu audio and saves to disk.
    """
    script = '''
    tell application "Audio Hijack" to activate
    delay 0.4
    tell application "System Events"
      tell process "Audio Hijack"
        click menu item "Run Session" of menu "Control" of menu bar 1
      end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=True, timeout=10)


def _newest_audio_file(directory: Path, since_mtime: float) -> Optional[Path]:
    """Return the freshest audio file in `directory` modified after `since_mtime`."""
    if not directory.exists():
        return None
    candidates = [
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS and p.stat().st_mtime > since_mtime
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--zone", default=DEFAULT_ZONE,
                        help=f"Zone id from zones.json (default: {DEFAULT_ZONE})")
    parser.add_argument("--speed-kmh", type=float, default=DEFAULT_SPEED_KMH)
    parser.add_argument("--duration-s", type=int, default=DEFAULT_DURATION_S,
                        help=f"Final trimmed video length, seconds (default: {DEFAULT_DURATION_S})")
    parser.add_argument("--home-seconds", type=int, default=DEFAULT_HOME_SECONDS,
                        help=f"Seconds to dwell on the Home InZoneCard before "
                             f"switching to Map (default: {DEFAULT_HOME_SECONDS})")
    parser.add_argument("--audio-dir", type=Path, default=None,
                        help="Audio Hijack Recorder output folder. If set, the "
                             "script toggles 'Control > Run Session' at start/stop "
                             "and muxes the newest audio file into the final video.")
    parser.add_argument("--keep-raw", action="store_true",
                        help="Keep the untrimmed raw recording next to the trimmed file")
    args = parser.parse_args()

    for dep in ("adb", "ffmpeg"):
        if not shutil.which(dep):
            sys.exit(f"{dep} not on PATH (brew install {dep})")
    if args.audio_dir and not args.audio_dir.exists():
        sys.exit(f"--audio-dir does not exist: {args.audio_dir}")

    device = AndroidDevice()
    device_mod.set_current(device)
    device.require_device()
    if not device.package_installed():
        sys.exit("SrednaBG not installed on the emulator — build & install the debug APK first")

    record_seconds = args.duration_s + RECORD_SAFETY_S
    pump_points = record_seconds
    print(f"==> Zone:         {args.zone}")
    print(f"==> Speed:        {args.speed_kmh:.0f} km/h")
    print(f"==> Video length: {args.duration_s} s  (home: {args.home_seconds} s, then map)")
    print(f"==> Audio:        {'Audio Hijack → ' + str(args.audio_dir) if args.audio_dir else 'OFF (silent video)'}")
    print(f"==> Recording:    {record_seconds} s cap; pump generates {pump_points} fixes @ 1 Hz")

    gpx_path = FIXTURES_DIR / f"{args.zone}_{int(args.speed_kmh)}_demo.gpx"
    if gpx_path.exists():
        gpx_path.unlink()
    build_no_approach_gpx(args.zone, args.speed_kmh, pump_points, gpx_path)
    print(f"==> GPX:          {gpx_path.name}")

    print("==> Pre-flight: grant perms, doze whitelist, force-stop, fresh launch, max volume, show-touches on")
    device.grant_runtime_permissions()
    _whitelist_battery_opt(device.package_id)
    device.force_stop()
    adb.shell("settings put system show_touches 1")
    _max_media_volume()
    device.start_main()
    time.sleep(3.0)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    on_device_video = "/sdcard/srednabg-demo-raw.mp4"
    video_raw_path = OUT_DIR / "srednabg-demo-raw.mp4"
    if video_raw_path.exists():
        video_raw_path.unlink()

    audio_start_mtime = time.time()
    audio_started = False
    rec_proc: Optional[subprocess.Popen] = None
    plan = parse_gpx(gpx_path)
    pump_thread = threading.Thread(target=pump, args=(plan,), daemon=True)

    try:
        # Start Audio Hijack first so the TTS at zone-entry is captured.
        if args.audio_dir:
            print("==> Audio Hijack: Control > Run Session (start)")
            _toggle_audio_hijack_session()
            audio_started = True
            time.sleep(0.5)  # let AH ramp the recorder

        print(f"==> Starting adb screenrecord for {record_seconds} s")
        rec_proc = subprocess.Popen([
            shutil.which("adb"), "shell", "screenrecord",
            "--bit-rate", "8000000",
            "--time-limit", str(record_seconds),
            on_device_video,
        ])

        # Settle on the Home screen so the recording opens with a stable frame.
        time.sleep(1.5)

        print("==> Tap Start tracking")
        _find_and_tap({"text": "Start tracking"}, {"text": "Стартирай"})
        time.sleep(0.8)  # let isTracking flip the button + render OutsideCard

        print(f"==> Pumping GPS in background; dwell {args.home_seconds} s on Home (InZoneCard + TTS)")
        pump_thread.start()
        time.sleep(args.home_seconds)

        print("==> Tap Map tab — switch to ZoneMapScreen (GPS already active, camera snaps to user)")
        _find_and_tap({"text": "Map"}, {"text": "Карта"}, {"resource_id": "tab-map"})

        print("==> Holding on Map until the recording cap is reached")
        wait_remaining = max(0.0, record_seconds - (1.5 + 0.8 + args.home_seconds + 1.0))
        time.sleep(wait_remaining)
    finally:
        if rec_proc is not None:
            rec_proc.send_signal(signal.SIGINT)
            try:
                rec_proc.wait(timeout=record_seconds + 10)
            except subprocess.TimeoutExpired:
                rec_proc.terminate()
                rec_proc.wait(timeout=5)
        if audio_started:
            try:
                print("==> Audio Hijack: Control > Run Session (stop)")
                _toggle_audio_hijack_session()
            except Exception as e:
                print(f"    (warning: failed to stop Audio Hijack: {e})")
        adb.shell("settings put system show_touches 0")
        try:
            device.stop_tracking()
        except Exception:
            pass

    print(f"==> Pulling raw video -> {video_raw_path.relative_to(REPO_ROOT)}")
    subprocess.run(
        [shutil.which("adb"), "pull", on_device_video, str(video_raw_path)],
        check=True, timeout=30,
    )
    adb.shell(f"rm {on_device_video}")

    # Find the audio file if recording was enabled.
    audio_path: Optional[Path] = None
    if args.audio_dir:
        # AH often finalizes the file ~1 s after stop. Poll briefly.
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            audio_path = _newest_audio_file(args.audio_dir, audio_start_mtime)
            if audio_path and audio_path.stat().st_size > 10_000:
                break
            time.sleep(0.5)
        if not audio_path:
            print(f"    (warning: no fresh audio file in {args.audio_dir}; shipping silent)")

    # Combine + trim.
    final_path = OUT_DIR / f"srednabg-demo-{args.duration_s}s.mp4"
    if audio_path:
        print(f"==> Muxing audio ({audio_path.name}) + video, trimming to {args.duration_s} s")
        subprocess.run([
            shutil.which("ffmpeg"), "-y", "-loglevel", "error",
            "-i", str(video_raw_path),
            "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(args.duration_s),
            str(final_path),
        ], check=True)
    else:
        print(f"==> Trimming to {args.duration_s} s (silent)")
        subprocess.run([
            shutil.which("ffmpeg"), "-y", "-loglevel", "error",
            "-i", str(video_raw_path),
            "-t", str(args.duration_s),
            "-c", "copy",
            str(final_path),
        ], check=True)

    if not args.keep_raw:
        video_raw_path.unlink(missing_ok=True)

    print()
    print(f"Done: {final_path}")
    print("Next: upload as Unlisted to YouTube, paste the URL into Play Console.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
