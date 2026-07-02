# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Thin wrappers around the `adb` CLI.

Stdlib only. Every function is sync; concurrency is the caller's problem.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

PACKAGE = "com.demosten.srednabg"
MAIN_ACTIVITY = f"{PACKAGE}/.app.ui.MainActivity"
SERVICE = f"{PACKAGE}/.app.service.LocationTrackingService"
DEBUG_SYNC_RECEIVER = f"{PACKAGE}/{PACKAGE}.app.debug.DebugSyncReceiver"
DEBUG_CONTROL_RECEIVER = f"{PACKAGE}/{PACKAGE}.app.debug.DebugControlReceiver"

ACTION_SYNC_MAP = "com.demosten.srednabg.debug.SYNC_MAP"
ACTION_SYNC_ZONES = "com.demosten.srednabg.debug.SYNC_ZONES"
ACTION_SET_SETTING = "com.demosten.srednabg.debug.SET_SETTING"
ACTION_DUMP_HISTORY = "com.demosten.srednabg.debug.DUMP_HISTORY"


def _adb() -> str:
    adb = shutil.which("adb")
    if not adb:
        raise RuntimeError("adb not found on PATH")
    return adb


def _run(args: list[str], *, timeout: float = 30.0, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_adb(), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


def devices() -> list[str]:
    out = _run(["devices"]).stdout.splitlines()
    return [ln.split()[0] for ln in out[1:] if ln.strip() and "device" in ln and "offline" not in ln]


def require_one_device() -> str:
    ds = devices()
    if not ds:
        raise RuntimeError("no adb devices attached. Boot the emulator first.")
    if len(ds) > 1:
        raise RuntimeError(f"multiple devices attached ({ds}); set ANDROID_SERIAL or detach the others")
    return ds[0]


def shell(cmd: str, *, timeout: float = 30.0) -> str:
    return _run(["shell", cmd], timeout=timeout).stdout


def shell_check(cmd: str, *, timeout: float = 30.0) -> tuple[int, str, str]:
    """Run shell command, return (returncode, stdout, stderr) without raising."""
    p = _run(["shell", cmd], timeout=timeout, check=False)
    return p.returncode, p.stdout, p.stderr


def package_installed(pkg: str = PACKAGE) -> bool:
    out = shell(f"pm list packages {pkg}")
    return f"package:{pkg}" in out


def boot_completed() -> bool:
    return shell("getprop sys.boot_completed").strip() == "1"


def wait_boot(timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if boot_completed():
            return
        time.sleep(2.0)
    raise TimeoutError("device did not finish booting")


def mute_audio() -> None:
    """Drop STREAM_MUSIC to zero on the emulator. Idempotent.

    Approaches that DO NOT work on this Pixel emulator and have wasted
    debugging time before:
    - `cmd audio set-master-mute true` — `cmd audio` only exposes
      surround-format commands here; the call is a silent no-op.
    - `cmd media_session volume --stream 3 --set 0` — affects registered
      MediaSessions, not OS stream volume; dumpsys still shows max.
    - `settings put system volume_music 0` — Settings provider isn't
      wired to AudioService volume state.

    What works: send 20× KEYCODE_VOLUME_DOWN, which AudioService treats
    as user input and walks STREAM_MUSIC down to 0 (also flipping its
    Muted flag). STREAM_TTS, STREAM_ACCESSIBILITY, and STREAM_ASSISTANT
    are aliased to STREAM_MUSIC, so muting MUSIC silences TTS regardless
    of which AudioAttributes USAGE the app picked.
    """
    for _ in range(20):
        shell_check("input keyevent 25")  # KEYCODE_VOLUME_DOWN


def unmute_audio() -> None:
    """Walk STREAM_MUSIC back up after `mute_audio`. Idempotent — 20×
    KEYCODE_VOLUME_UP overshoots to the max, which is the desired restore
    point for a freshly-muted emulator (the inverse of `mute_audio`'s 20×
    VOLUME_DOWN). Symmetric so a validation run leaves audio as it found it."""
    for _ in range(20):
        shell_check("input keyevent 24")  # KEYCODE_VOLUME_UP


def grant_runtime_permissions(pkg: str = PACKAGE) -> None:
    """Pre-grant the runtime permissions the app needs so the harness
    doesn't have to dismiss permission dialogs in the middle of a run."""
    perms = [
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_BACKGROUND_LOCATION",
        "android.permission.POST_NOTIFICATIONS",
    ]
    for p in perms:
        # Some perms are not requested in some manifests; ignore failures.
        shell_check(f"pm grant {pkg} {p}")


def install_apk(apk_path: Path) -> None:
    if not apk_path.exists():
        raise FileNotFoundError(apk_path)
    _run(["install", "-r", "-g", str(apk_path)], timeout=180.0)


def force_stop(pkg: str = PACKAGE) -> None:
    shell(f"am force-stop {pkg}")


def start_main(pkg: str = PACKAGE) -> None:
    shell(f"am start -n {MAIN_ACTIVITY}")


def start_tracking_service() -> None:
    """Foreground the LocationTrackingService so onStartCommand runs."""
    shell(f"am start-foreground-service -n {SERVICE}")


def app_running(pkg: str = PACKAGE) -> bool:
    return shell(f"pidof {pkg}").strip() != ""


def broadcast(action: str, receiver: str, extras: Optional[dict[str, str]] = None,
              *, timeout: float = 60.0) -> str:
    """am broadcast wrapper. Extras must be string-typed.

    am broadcast blocks until the receiver's goAsync() PendingResult finishes.
    DebugSyncReceiver does network I/O inside goAsync, so on flaky connectivity
    (e.g. the zones_offline scenario) it can sit on OkHttp's ~30s socket timeout
    before returning. Default timeout is bumped to 60s to stay ahead of that.
    """
    extra_args = ""
    if extras:
        extra_args = " " + " ".join(f'--es {k} "{v}"' for k, v in extras.items())
    return shell(f"am broadcast -n {receiver} -a {action}{extra_args}", timeout=timeout)


def dump_history() -> str:
    """Ask DebugControlReceiver to log the history count + latest-record summary.

    Android-only (talks straight to DebugControlReceiver, like the manual
    zone-feeding tools). The `DUMP_HISTORY …` line lands on tag DebugSettings,
    parsed into a `HistoryDump` event.
    """
    return broadcast(ACTION_DUMP_HISTORY, DEBUG_CONTROL_RECEIVER)


def geo_fix(lng: float, lat: float) -> None:
    """Push a single mock GPS fix via the emulator console.

    Note: lng comes BEFORE lat in `geo fix` (qemu legacy). We do not pass
    velocity — the emulator ignores it on most builds and FLP synthesizes
    speed/bearing from successive positions, which is what the Kalman
    filter expects anyway.
    """
    _run(["emu", "geo", "fix", f"{lng:.7f}", f"{lat:.7f}"], timeout=5.0)


def dumpsys(service: str) -> str:
    return shell(f"dumpsys {service}", timeout=20.0)


def list_notifications() -> str:
    """Filtered dumpsys output relevant to our notification channel."""
    return dumpsys("notification --noredact")


def set_data_enabled(enabled: bool) -> None:
    shell(f"svc data {'enable' if enabled else 'disable'}")


def set_wifi_enabled(enabled: bool) -> None:
    shell(f"svc wifi {'enable' if enabled else 'disable'}")


def app_files_dir(pkg: str = PACKAGE) -> str:
    """Returns the app's filesDir path (requires debuggable build)."""
    return f"/data/data/{pkg}/files"


def run_as_read(pkg: str, relative_path: str) -> str:
    """Read a file from inside the app's private storage. Requires debug build."""
    return shell(f"run-as {pkg} cat {relative_path}")


def run_as_ls(pkg: str, relative_path: str) -> str:
    return shell(f"run-as {pkg} ls -la {relative_path}")


def file_exists_in_app(pkg: str, relative_path: str) -> bool:
    rc, _, _ = shell_check(f"run-as {pkg} test -e {relative_path}")
    return rc == 0


def clear_logcat() -> None:
    _run(["logcat", "-c"])


def logcat_dump(*filters: str, timeout: float = 30.0) -> str:
    """Snapshot the main logcat buffer and return. `filters` are passed
    straight through (e.g. "-s", "SrednaBG.TTS:D"). Never raises on a
    non-zero exit (a stale filter just yields no lines)."""
    return _run(["logcat", "-d", *filters], check=False, timeout=timeout).stdout


def push(local: str, remote: str, *, timeout: float = 60.0) -> None:
    _run(["push", local, remote], timeout=timeout)


def get_state() -> Optional[str]:
    """`adb get-state` — returns the state string (e.g. "device") or None
    when no device is attached. Does not raise."""
    p = _run(["get-state"], check=False, timeout=10.0)
    return p.stdout.strip() if p.returncode == 0 else None


def crash_buffer() -> str:
    """Snapshot of the crash buffer since boot. Empty string when clean."""
    p = _run(["logcat", "-b", "crash", "-d", "-v", "time"], check=False)
    return p.stdout


def clear_crash_buffer() -> None:
    """Clear the crash buffer. Called per-scenario so each `expect_crash_free`
    only sees crashes that happened during its own scenario."""
    _run(["logcat", "-b", "crash", "-c"], check=False)
