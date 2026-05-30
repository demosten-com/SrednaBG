#!/usr/bin/env bash
#
# Builds a versioned, SHA-256-pinned map bundle for an F-Droid release.
#
# Per-release immutability is required because F-Droid's build sandbox fetches
# the bundle by URL and verifies the hash. The hosted `map-bundle.zip` (no
# version suffix) is mutable across releases; this script produces a
# `map-bundle-<tag>.zip` that never changes.
#
# Usage:
#   bash web/fdroid/scripts/publish-map-bundle.sh <tag>
#
# Example:
#   bash web/fdroid/scripts/publish-map-bundle.sh v1.0.2
#
# Does NOT auto-upload. Prints the scp command for manual upload to Namecheap
# (no upload automation is wired up; see project_web_hosting.md).
#
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <tag>" >&2
    echo "example: $0 v1.0.2" >&2
    exit 64
fi

TAG="$1"
if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "error: tag must look like v1.2.3 (got: $TAG)" >&2
    exit 64
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
BUILD_SCRIPT="$REPO_ROOT/backend/scripts/build-map-bundle.sh"
DATA_DIR="$REPO_ROOT/backend/data"
SRC_ZIP="$DATA_DIR/map-bundle.zip"
VERSIONED_ZIP="$DATA_DIR/map-bundle-${TAG}.zip"
CHECKSUMS_FILE="$REPO_ROOT/web/fdroid/map-bundle-checksums.txt"

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

echo "==> Copying to versioned filename"
cp "$SRC_ZIP" "$VERSIONED_ZIP"

echo "==> Computing SHA-256"
SHA256=$(shasum -a 256 "$VERSIONED_ZIP" | awk '{print $1}')
SHA_SIDECAR="${VERSIONED_ZIP}.sha256"
printf '%s  %s\n' "$SHA256" "map-bundle-${TAG}.zip" > "$SHA_SIDECAR"

echo "==> Updating $CHECKSUMS_FILE"
TMP="$(mktemp)"
grep -v "[[:space:]]${TAG}\$" "$CHECKSUMS_FILE" 2>/dev/null > "$TMP" || true
printf '%s  %s\n' "$SHA256" "$TAG" >> "$TMP"
mv "$TMP" "$CHECKSUMS_FILE"

SIZE=$(ls -lh "$VERSIONED_ZIP" | awk '{print $5}')

cat <<EOF

================================================================================
  Map bundle built and hashed.

  Tag:        $TAG
  File:       $VERSIONED_ZIP ($SIZE)
  SHA-256:    $SHA256
  Sidecar:    $SHA_SIDECAR
  Checksums:  $CHECKSUMS_FILE (updated)

  NEXT STEPS (manual — no upload automation):

  1. Upload to Namecheap. Replace USER and HOST with your SFTP credentials
     (see project_web_hosting.md for the docroot):

       scp "$VERSIONED_ZIP" USER@HOST:srednabg_com/assets/

  2. Verify the upload:

       curl -fsI https://srednabg.com/assets/map-bundle-${TAG}.zip

  3. Paste this SHA-256 into web/fdroid/metadata.yml, replacing
     '<SHA256-pinned-at-tag-time>' in the Builds[] entry for $TAG:

       $SHA256

  4. Commit the updated web/fdroid/map-bundle-checksums.txt and metadata.yml.
================================================================================
EOF
