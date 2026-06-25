#!/usr/bin/env bash
# Boot the Pixel_8a AVD headless and block until Android has fully booted.
# Requires `adb` and `emulator` on PATH (see .github/SELF_HOSTED_RUNNER.md).
set -euo pipefail

AVD="${SREDNABG_AVD:-Pixel_8a}"

# Already-booted device? Reuse it (idempotent across re-runs on the runner).
if adb devices | grep -qE 'emulator-[0-9]+\s+device'; then
  echo "An emulator is already running — reusing it."
else
  echo "Booting AVD '$AVD' headless..."
  # -no-window keeps it off the desktop; swiftshader_indirect renders without a
  # GPU surface; -no-snapshot guarantees a clean cold boot each run.
  emulator -avd "$AVD" -no-window -no-audio -no-boot-anim -no-snapshot \
    -gpu swiftshader_indirect -accel auto >"${RUNNER_TEMP:-/tmp}/emulator.log" 2>&1 &
fi

echo "Waiting for device..."
adb wait-for-device

echo "Waiting for sys.boot_completed..."
for _ in $(seq 1 120); do
  if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
    break
  fi
  sleep 3
done

if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != "1" ]; then
  echo "::error::Emulator did not finish booting in time."
  exit 1
fi

# Dismiss the keyguard so UI scenarios/screenshots aren't behind the lock screen.
adb shell input keyevent 82 || true
echo "Emulator booted."
