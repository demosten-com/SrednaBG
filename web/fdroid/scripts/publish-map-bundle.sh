#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — web / fdroid

# Rebuilds the offline map bundle, refreshes the single pinned digest, and
# publishes the new latest to the rolling GitHub Release.
#
# Model (GitHub-only, since 2026-06-12): the rolling `map-bundle-latest`
# release holds ONE mutable `map-bundle.zip` (the latest). At tag time,
# .github/workflows/android-release.yml downloads it, verifies it against the
# digest this script pins, and snapshots it into the version's GitHub Release
# as an immutable `map-bundle-<tag>.zip` — the durable build input F-Droid's
# prebuild fetches. So you only run this when the MAP CONTENT actually
# changes, not on every release. (Replaces the former Namecheap-hosted
# srednabg.com/assets/map-bundle.zip staging copy.)
#
# It rebuilds the bundle, computes its SHA-256, writes that single digest into
# web/fdroid/map-bundle-checksums.txt (the one pinned source of truth —
# backend/scripts/fetch-fdroid-map-bundle.sh reads it at build time), and
# uploads `map-bundle.zip` (+`.sha256`) to the `map-bundle-latest` release
# with `gh release upload --clobber` (creating the release if missing).
#
# Usage:
#   bash web/fdroid/scripts/publish-map-bundle.sh
#
# Needs an authenticated `gh` CLI. Commit the re-pinned checksums file after.
#
set -euo pipefail

ROLLING_TAG="map-bundle-latest"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
BUILD_SCRIPT="$REPO_ROOT/backend/scripts/build-map-bundle.sh"
DATA_DIR="$REPO_ROOT/backend/data"
SRC_ZIP="$DATA_DIR/map-bundle.zip"
CHECKSUMS_FILE="$REPO_ROOT/web/fdroid/map-bundle-checksums.txt"

if [[ ! -x "$BUILD_SCRIPT" && ! -f "$BUILD_SCRIPT" ]]; then
    echo "error: build-map-bundle.sh not found at $BUILD_SCRIPT" >&2
    exit 1
fi
if ! command -v gh &>/dev/null; then
    echo "error: 'gh' (GitHub CLI) is required to upload to the rolling release." >&2
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

echo "==> Uploading to the rolling '$ROLLING_TAG' GitHub Release"
# The .sha256 sidecar goes to a temp dir: backend/data/ gitignores only the
# zip itself, and the asset must be named map-bundle.zip.sha256.
SHA_DIR="$(mktemp -d)"
trap 'rm -rf "$SHA_DIR"' EXIT
printf '%s  %s\n' "$SHA256" "map-bundle.zip" > "$SHA_DIR/map-bundle.zip.sha256"
cd "$REPO_ROOT"
if ! gh release view "$ROLLING_TAG" >/dev/null 2>&1; then
    gh release create "$ROLLING_TAG" \
        --prerelease \
        --title "Offline map bundle (latest)" \
        --notes "Rolling staging asset, not an app release. The current offline map bundle; replaced in place whenever the map content changes (web/fdroid/scripts/publish-map-bundle.sh). At tag time the release workflow snapshots it into the version's immutable map-bundle-<tag>.zip. Expected SHA-256 is pinned in web/fdroid/map-bundle-checksums.txt."
fi
gh release upload "$ROLLING_TAG" "$SRC_ZIP" "$SHA_DIR/map-bundle.zip.sha256" --clobber

SIZE=$(ls -lh "$SRC_ZIP" | awk '{print $5}')
REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner)

cat <<EOF

================================================================================
  Map bundle rebuilt, pinned, and published.

  File:       $SRC_ZIP ($SIZE)
  SHA-256:    $SHA256
  Pinned in:  web/fdroid/map-bundle-checksums.txt
              (read at build time by backend/scripts/fetch-fdroid-map-bundle.sh)
  Uploaded:   https://github.com/$REPO_SLUG/releases/download/$ROLLING_TAG/map-bundle.zip

  NEXT STEPS:

  1. Verify the published asset hashes to the value above:

       curl -fsSL https://github.com/$REPO_SLUG/releases/download/$ROLLING_TAG/map-bundle.zip | shasum -a 256

  2. Commit the pinned checksums file. The next tag's release workflow will
     snapshot this bundle into map-bundle-<tag>.zip on the GitHub Release
     automatically.
================================================================================
EOF
