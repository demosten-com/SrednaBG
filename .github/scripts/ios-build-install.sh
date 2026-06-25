#!/usr/bin/env bash
# Build the iOS Debug app for the Simulator, boot a Simulator, and install it.
# The QA harness's IosDevice talks to a loopback debug listener that only exists
# in Debug builds and auto-detects the booted Simulator. Run from the repo root.
#
# Requires a logged-in GUI session on the Mac mini — the Simulator needs Metal
# (no headless mode). See .github/SELF_HOSTED_RUNNER.md.
set -euo pipefail

DERIVED="${RUNNER_TEMP:-/tmp}/srednabg-ios-qa"

echo "Building iOS Debug app (Simulator, no signing)..."
xcodebuild -scheme SrednaBG -project ios/SrednaBG.xcodeproj \
  -configuration Debug -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$DERIVED" CODE_SIGNING_ALLOWED=NO build

APP=$(find "$DERIVED/Build/Products/Debug-iphonesimulator" -maxdepth 1 -name '*.app' | head -1)
if [ -z "$APP" ]; then
  echo "::error::built .app not found under $DERIVED/Build/Products/Debug-iphonesimulator"
  exit 1
fi
echo "Built: $APP"

# Reuse an already-booted Simulator, else boot the first available iPhone.
UDID=$(xcrun simctl list devices booted | grep -oE '[0-9A-Fa-f-]{36}' | head -1 || true)
if [ -z "$UDID" ]; then
  UDID=$(xcrun simctl list devices available | grep -E 'iPhone' | grep -oE '[0-9A-Fa-f-]{36}' | head -1 || true)
  if [ -z "$UDID" ]; then
    echo "::error::no available iPhone Simulator. Install an iOS runtime via Xcode."
    exit 1
  fi
  echo "Booting Simulator $UDID ..."
  xcrun simctl bootstatus "$UDID" -b
fi
echo "Using Simulator $UDID"

xcrun simctl install "$UDID" "$APP"
echo "Installed iOS Debug app on $UDID."
