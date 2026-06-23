#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# feed-zone.sh — drive a bundled average-speed zone on the running emulator by
# injecting GPS fixes through the debug build's DebugControlReceiver.
#
# Run with no zone        -> lists the available zones (idx / id / road / limit).
# Run with a zone         -> starts tracking and feeds a route that approaches
#   (index, id, or an        the zone from outside, drives through it, and exits,
#    unambiguous substring)   so you walk the full Outside -> InZone -> Exiting.
#
#   qa/feed-zone.sh                 # list zones
#   qa/feed-zone.sh 0               # feed zone index 0
#   qa/feed-zone.sh europa-01-east  # feed by id
#   qa/feed-zone.sh trakiya         # feed by substring (must be unambiguous)
#
# Env overrides: SPEED_MS (default 30 ~108km/h)  STEP_M (30)  INTERVAL (1s)
#                PKG (com.demosten.srednabg)  ZONES_JSON (path)  NO_START=1
#
# Requires the DEBUG build installed and ACCESS_FINE/BACKGROUND_LOCATION granted.
# For the overlay specifically, also `appops set <pkg> SYSTEM_ALERT_WINDOW allow`,
# enable it (SET_SETTING overlay_enabled true), and press Home so the app is
# backgrounded while the route plays.
set -euo pipefail

PKG="${PKG:-com.demosten.srednabg}"
RC="$PKG/$PKG.app.debug.DebugControlReceiver"
SPEED_MS="${SPEED_MS:-30}"
STEP_M="${STEP_M:-30}"
INTERVAL="${INTERVAL:-1}"
NO_START="${NO_START:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ZONES_JSON="${ZONES_JSON:-$REPO_ROOT/backend/data/zones.json}"
HELPER="$SCRIPT_DIR/feed_zone.py"

case "${1:-}" in
    -h|--help)
        grep '^#' "${BASH_SOURCE[0]}" | sed '1d;s/^# \{0,1\}//'
        exit 0
        ;;
    --no-start)
        NO_START=1; shift
        ;;
esac
SELECTOR="${1:-}"

[[ -f "$ZONES_JSON" ]] || { echo "zones.json not found at: $ZONES_JSON (set ZONES_JSON=...)" >&2; exit 1; }

adb get-state >/dev/null 2>&1 || { echo "no adb device — boot the Pixel_8a emulator first" >&2; exit 1; }

# No zone selected -> list and exit (does not touch the device).
if [[ -z "$SELECTOR" || "$SELECTOR" == "list" ]]; then
    python3 "$HELPER" list "$ZONES_JSON"
    exit 0
fi

# Build the route first so an unknown selector fails before we start tracking.
ROUTE="$(python3 "$HELPER" route "$ZONES_JSON" "$SELECTOR" "$STEP_M" "$SPEED_MS")"

if [[ "$NO_START" != "1" ]]; then
    # Foreground the app first. START_TRACKING starts a foreground service from a
    # background broadcast receiver, which Android 12+ denies unless the app is in
    # an allowed state (a visible activity → PROC_STATE_TOP). Without this the FGS
    # start is silently denied and no fixes are ever processed.
    echo "Foregrounding the app…"
    adb shell am start -W -a android.intent.action.MAIN \
        -c android.intent.category.LAUNCHER \
        -n "$PKG/.app.ui.MainActivity" >/dev/null 2>&1
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        adb shell dumpsys activity activities 2>/dev/null \
            | grep -q "ResumedActivity.*$PKG" && break
        sleep 0.5
    done
    echo "Starting tracking…"
    adb shell am broadcast -n "$RC" -a com.demosten.srednabg.debug.START_TRACKING >/dev/null 2>&1
    sleep 2
fi

echo "Feeding route (Ctrl-C to stop):"
n=0
while IFS=$'\t' read -r lat lng spd br; do
    [[ -z "$lat" ]] && continue
    # </dev/null: adb reads stdin, which would otherwise swallow the rest of
    # the here-string route and stop the loop after the first fix.
    adb shell am broadcast -n "$RC" -a com.demosten.srednabg.debug.FEED_POINT \
        --es lat "$lat" --es lng "$lng" --es speed_ms "$spd" --es bearing "$br" </dev/null >/dev/null 2>&1
    n=$((n + 1))
    printf '.'
    sleep "$INTERVAL"
done <<< "$ROUTE"
echo
echo "Done — fed $n fixes. Stop with:"
echo "  adb shell am broadcast -n $RC -a com.demosten.srednabg.debug.STOP_TRACKING"
