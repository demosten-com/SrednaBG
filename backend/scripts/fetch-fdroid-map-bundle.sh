#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — backend / scripts

# Fetches + SHA-256-verifies the offline map bundle for F-Droid's build sandbox.
# Called from the `prebuild` step of the F-Droid recipe
# (web/fdroid/metadata.yml -> fdroiddata metadata/com.demosten.srednabg.yml).
#
# Why a script instead of inline prebuild commands: the curl (flags + URL) and
# the sha256sum line (64-char digest) both exceed F-Droid's metadata line
# width. `fdroid rewritemeta` folds long lines, and that fold collides with the
# trailing-spaces lint — so a single short `bash ...` call is the only form that
# satisfies both rewritemeta and lint. The URL + digest stay auditable here, in
# the repo at the build tag.
#
# The bundle is the immutable per-tag asset that android-release.yml attaches to
# the GitHub Release (durable as the source itself). The tag is derived from the
# literal versionName, so this script needs NO per-release edit — only SHA256
# changes, and only when the map bundle is actually rebuilt (matches the
# `map-bundle.zip` line in web/fdroid/map-bundle-checksums.txt).
set -euo pipefail

SHA256="0513907ed5108c34a5a13646f5c4dc8968c44f372587bef888543c80b757bcd1"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
DATA_DIR="$SCRIPT_DIR/../data"
ZIP="$DATA_DIR/map-bundle.zip"

# Derive vX.Y.Z from the build's own versionName so the URL tracks the tag.
VN="$(grep -oE 'versionName = "[0-9]+\.[0-9]+\.[0-9]+"' "$REPO_ROOT/android/app/build.gradle.kts" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
if [ -z "$VN" ]; then
  echo "fetch-fdroid-map-bundle: could not read versionName from android/app/build.gradle.kts" >&2
  exit 1
fi
URL="https://github.com/demosten-com/SrednaBG/releases/download/v${VN}/map-bundle-v${VN}.zip"

mkdir -p "$DATA_DIR"
curl -fsSL --http1.1 --retry 5 --retry-delay 3 --retry-all-errors -o "$ZIP" "$URL"
echo "$SHA256  $ZIP" | sha256sum -c -
rm -rf "$DATA_DIR/map-bundle"
unzip -q "$ZIP" -d "$DATA_DIR/map-bundle"
rm "$ZIP"
