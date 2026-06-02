#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — web / fdroid

# Rebuilds the offline map bundle and refreshes the single pinned digest.
#
# New model (no per-tag bundles here): the web host serves ONE mutable
# `map-bundle.zip` (the latest). At tag time, .github/workflows/android-release.yml
# downloads it, verifies it against the digest this script pins, and snapshots it
# into the GitHub Release as an immutable `map-bundle-<tag>.zip` — the durable
# build input F-Droid's prebuild fetches. So you only run this when the MAP
# CONTENT actually changes, not on every release.
#
# It rebuilds the bundle, computes its SHA-256, writes that single digest into
# BOTH web/fdroid/map-bundle-checksums.txt and backend/scripts/fetch-fdroid-map-bundle.sh
# (kept in sync), and prints the scp command to publish the new latest.
#
# Usage:
#   bash web/fdroid/scripts/publish-map-bundle.sh
#
# Does NOT auto-upload. Prints the scp command for manual upload to Namecheap
# (no upload automation is wired up; see project_web_hosting.md).
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
BUILD_SCRIPT="$REPO_ROOT/backend/scripts/build-map-bundle.sh"
DATA_DIR="$REPO_ROOT/backend/data"
SRC_ZIP="$DATA_DIR/map-bundle.zip"
CHECKSUMS_FILE="$REPO_ROOT/web/fdroid/map-bundle-checksums.txt"
FETCH_SCRIPT="$REPO_ROOT/backend/scripts/fetch-fdroid-map-bundle.sh"

if [[ ! -x "$BUILD_SCRIPT" && ! -f "$BUILD_SCRIPT" ]]; then
    echo "error: build-map-bundle.sh not found at $BUILD_SCRIPT" >&2
    exit 1
fi

echo "==> Building map bundle (generates tiles with Planetiler; needs Java 21+, no tileserver-gl/Docker)"
bash "$BUILD_SCRIPT"

if [[ ! -f "$SRC_ZIP" ]]; then
    echo "error: build did not produce $SRC_ZIP" >&2
    exit 1
fi

echo "==> Computing SHA-256"
SHA256=$(shasum -a 256 "$SRC_ZIP" | awk '{print $1}')

echo "==> Pinning digest in $CHECKSUMS_FILE"
TMP="$(mktemp)"
grep -v "[[:space:]]map-bundle\.zip\$" "$CHECKSUMS_FILE" 2>/dev/null > "$TMP" || true
printf '%s  %s\n' "$SHA256" "map-bundle.zip" >> "$TMP"
mv "$TMP" "$CHECKSUMS_FILE"

echo "==> Pinning digest in $FETCH_SCRIPT"
# Keep the F-Droid prebuild's hardcoded SHA256 in sync with the checksums file.
perl -i -pe "s/^SHA256=\"[a-f0-9]{64}\"/SHA256=\"$SHA256\"/" "$FETCH_SCRIPT"

SIZE=$(ls -lh "$SRC_ZIP" | awk '{print $5}')

cat <<EOF

================================================================================
  Map bundle rebuilt and pinned.

  File:       $SRC_ZIP ($SIZE)
  SHA-256:    $SHA256
  Pinned in:  web/fdroid/map-bundle-checksums.txt
              backend/scripts/fetch-fdroid-map-bundle.sh

  NEXT STEPS (manual — no upload automation):

  1. Publish the new latest bundle to Namecheap. Replace USER and HOST with your
     SFTP credentials (see project_web_hosting.md for the docroot):

       scp "$SRC_ZIP" USER@HOST:srednabg_com/assets/map-bundle.zip

  2. Verify the upload hashes to the value above:

       curl -fsSL https://srednabg.com/assets/map-bundle.zip | shasum -a 256

  3. Commit the two pinned files. The next tag's release workflow will snapshot
     this bundle into map-bundle-<tag>.zip on the GitHub Release automatically.
================================================================================
EOF
