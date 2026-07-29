#!/usr/bin/env bash
# Assemble the gms debug APK and (re)install it on the booted emulator. The QA
# harness deliberately does not build or install — this does it first. QA on the
# emulator uses the gms flavor (FusedLocationProvider) per project convention.
# Run from the repo root with an emulator already booted.
set -euo pipefail

cd android
chmod +x gradlew
./gradlew :app:assembleGmsDebug --stacktrace
cd ..

APK=android/app/build/outputs/apk/gms/debug/app-gms-debug.apk
if [ ! -f "$APK" ]; then
  echo "::error::Expected APK not found at $APK"
  exit 1
fi

echo "Installing $APK ..."
adb install -r -d "$APK"
echo "Installed com.demosten.srednabg (gms debug)."
