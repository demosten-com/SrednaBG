#!/usr/bin/env bash
# Wire the Android SDK + full Xcode into the job environment. The GitHub Actions
# runner on the mini runs as a LaunchAgent whose PATH/env does NOT match an
# interactive shell, so ANDROID_HOME / adb / the Xcode toolchain aren't visible
# by default. This resolves them from the machine (they ARE installed) and
# exports to GITHUB_ENV / GITHUB_PATH for subsequent steps.
#
# Pass `android`, `xcode`, or both as args to select what to wire.
set -euo pipefail

SELECT="${*:-android xcode}"
want() { case " $SELECT " in *" $1 "*) return 0;; esac; return 1; }

if want android "$SELECT"; then
  if [ -z "${ANDROID_HOME:-}" ]; then
    for c in "${ANDROID_SDK_ROOT:-}" "$HOME/Library/Android/sdk" \
             "/usr/local/share/android-sdk" "/opt/homebrew/share/android-commandlinetools"; do
      if [ -n "$c" ] && [ -d "$c/platform-tools" ]; then ANDROID_HOME="$c"; break; fi
    done
  fi
  if [ -n "${ANDROID_HOME:-}" ] && [ -d "$ANDROID_HOME/platform-tools" ]; then
    echo "ANDROID_HOME=$ANDROID_HOME"
    {
      echo "ANDROID_HOME=$ANDROID_HOME"
      echo "ANDROID_SDK_ROOT=$ANDROID_HOME"
    } >> "$GITHUB_ENV"
    {
      echo "$ANDROID_HOME/platform-tools"
      echo "$ANDROID_HOME/emulator"
      echo "$ANDROID_HOME/cmdline-tools/latest/bin"
    } >> "$GITHUB_PATH"
  else
    echo "::error::Android SDK not found. Install it or set ANDROID_HOME on the runner."
    exit 1
  fi
fi

if want xcode "$SELECT"; then
  # SwiftLint/xcodebuild need full Xcode's toolchain (sourcekitdInProc lives
  # there); the CommandLineTools path lacks it. Prefer the active selection if
  # it's a real Xcode.app, else fall back to the default install location.
  DEV="$(xcode-select -p 2>/dev/null || true)"
  case "$DEV" in
    *CommandLineTools*|"") DEV="" ;;
  esac
  if [ -z "$DEV" ] && [ -d "/Applications/Xcode.app/Contents/Developer" ]; then
    DEV="/Applications/Xcode.app/Contents/Developer"
  fi
  if [ -n "$DEV" ]; then
    echo "DEVELOPER_DIR=$DEV"
    echo "DEVELOPER_DIR=$DEV" >> "$GITHUB_ENV"
  else
    echo "::error::Full Xcode not found. Install Xcode (not just CommandLineTools) on the runner."
    exit 1
  fi
fi
