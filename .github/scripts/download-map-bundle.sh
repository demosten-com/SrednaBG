#!/usr/bin/env bash
# Fetch + unzip the offline map bundle into backend/data/map-bundle so the
# Android build's prepareMapAssets/validateMapBundle tasks find it. Run from the
# repo root. MAP_BUNDLE_URL (optional secret) overrides the default rolling
# map-bundle-latest release asset. Mirrors the logic in android-build.yml /
# android-release.yml — keep the required-file list in sync with
# `requiredMapFiles` in android/app/build.gradle.kts.
set -euo pipefail

mkdir -p backend/data
URL="${MAP_BUNDLE_URL:-https://github.com/${GITHUB_REPOSITORY}/releases/download/map-bundle-latest/map-bundle.zip}"
echo "Downloading map bundle: $URL"
curl -fsSL "$URL" -o backend/data/map-bundle.zip
unzip -q -o backend/data/map-bundle.zip -d backend/data/map-bundle

for f in style-light.json style-dark.json bulgaria.mbtiles; do
  if [ ! -f "backend/data/map-bundle/$f" ]; then
    echo "::error::map-bundle.zip is missing $f. Regenerate + republish with 'bash web/fdroid/scripts/publish-map-bundle.sh'."
    exit 1
  fi
done
echo "Map bundle ready."
