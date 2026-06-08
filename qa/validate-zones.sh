#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# validate-zones.sh — thin wrapper around validate_zones.py.
#
# Drives every bundled zone through the running emulator the way feed-zone.sh
# does (oriented by start/end endpoints = the real carriageway direction) and
# asserts, from the app's zone-state log, that each zone enters the *correct*
# zone, does not flap, and exits cleanly. By default it forces the device
# offline and clears app data so the *bundled* zones.json is what gets tested
# (otherwise zone sync replaces it with whatever the live server serves).
#
#   qa/validate-zones.sh                 # all zones, full traversal
#   qa/validate-zones.sh --quick         # ~2 km per zone (fast smoke)
#   qa/validate-zones.sh --only 0,1,5    # a subset (index or id)
#   qa/validate-zones.sh --keep-online   # test the device's current data as-is
#
# Requires the DEBUG build installed. Exit code 0 = all zones passed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/validate_zones.py" "$@"
