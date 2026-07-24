#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — web

# update_screenshots.sh — copy raw screenshots from web/screenshots/<platform>/
# into the marketing site's positional slots at web/html/screenshots/<platform>/<lang>/phone_NN.png.
#
# Source PNGs are produced by /screenshot-app (qa/srednabg_screenshots.py).
# web/screenshots/ is gitignored — regenerate before running this script.
#
# The marketing site uses 7 phone slots per language; the capture harness
# produces 10 NN shots (see qa/screenshots/shots.yaml). MAPPING below picks
# which (shot, theme) lands in which slot. Edit it freely.

set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$WEB_DIR/screenshots"
DST="$WEB_DIR/html/screenshots"

# Each entry: "slot shot theme"
#   slot  — output file phone_NN.png (what indexx.html references, 1-based)
#   shot  — source NN from /screenshot-app (1-based per shots.yaml order)
#   theme — light | dark (which captured theme variant to use)
MAPPING=(
  "01 01 light"   # home-outside-90        — Home, outside zone, 90 km/h
  "02 05 dark"    # map-heading-yellow-dark — Map yellow heading-up, dark theme
  "03 07 light"   # map-heading-red-light   — Map red over-limit, light theme
  "04 09 light"   # map-north-green        — Map green normal heading, light
  "05 10 dark"    # map-overview            — Bulgaria-wide overview, dark theme
  "06 04 light"   # map-north-green        — Map green normal heading, light
  "07 08 dark"    # settings-top            — Settings tab
  "08 11 light"   # history-tab            — History tab
  "09 12 dark"    # history-details        — History details
)

PLATFORMS=(android ios)
LANGS=(en bg)

copied=0
missing=0
for platform in "${PLATFORMS[@]}"; do
  for lang in "${LANGS[@]}"; do
    mkdir -p "$DST/$platform/$lang"
    for entry in "${MAPPING[@]}"; do
      read -r slot shot theme <<< "$entry"
      src="$SRC/$platform/$shot-$platform-$theme-$lang.png"
      dst="$DST/$platform/$lang/phone_$slot.png"
      if [[ ! -f "$src" ]]; then
        echo "  MISSING $src"
        missing=$((missing + 1))
        continue
      fi
      cp "$src" "$dst"
      echo "  $platform/$lang/phone_$slot.png  ←  $shot-$platform-$theme-$lang.png"
      copied=$((copied + 1))
    done
  done
done

echo
echo "Copied $copied file(s); $missing missing."
if [[ $missing -gt 0 ]]; then
  echo "Re-run /screenshot-app for any missing shots, then re-run this script."
  exit 1
fi
