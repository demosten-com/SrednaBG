#!/usr/bin/env bash
# Build the offline map bundle that ships inside the Android APK and iOS app.
#
# Self-contained: downloads everything it needs (the pinned Planetiler jar and,
# via Planetiler, the Geofabrik Bulgaria OSM extract), generates the vector
# tiles, assembles the bundle from the in-repo static assets, and cleans up all
# scratch data at the end — leaving ONLY the bundle. No Docker and no tile
# server required.
#
# Produces:
#   backend/data/map-bundle/          — unzipped tree staged into APK / iOS assets
#     ├── style-light.json            (vendored template, {MBTILES_URI} placeholder)
#     ├── style-dark.json             (derived from light)
#     ├── fonts/<fontstack>/<range>.pbf (vendored glyphs)
#     ├── bulgaria.mbtiles            (freshly generated, z5–z12)
#     └── version.json                ({"version": ..., "map_hash": "sha256:..."})
#   backend/data/map-bundle.zip       — zipped bundle served at /api/map/bundle.zip
#
# Runtime (Android/iOS) picks style-light.json or style-dark.json per the
# day/night resolver + Map-theme preference, then replaces {MBTILES_URI} /
# {GLYPHS_URI} / {SPRITE_URI} with absolute on-disk paths.
#
# The static style + glyphs live in backend/map-assets/ (see its LICENSE-NOTES.md);
# only bulgaria.mbtiles changes between map updates, so the build just regenerates
# the tiles from the latest OSM and re-packs.
#
# Prerequisites: java (>=21), jq, curl, zip, shasum, python3. ~4 GB free RAM and
# ~2 GB free scratch disk for tile generation.
#
# Usage:
#   bash build-map-bundle.sh [--keep-tiles]
#     --keep-tiles  also copy the generated mbtiles to backend/tiles/bulgaria.mbtiles
#                   (a standalone copy for inspection / other tooling). Default: don't.

set -euo pipefail

# --- Pins ---------------------------------------------------------------------
PLANETILER_VERSION="0.10.2"
PLANETILER_SHA256="f310bd0413e2e4512b27f4046d418664e8e1d3bf31603c2a70e23de06c167e4d"
PLANETILER_URL="https://github.com/onthegomap/planetiler/releases/download/v${PLANETILER_VERSION}/planetiler.jar"
JAVA_MIN_MAJOR=21

# --- Args ---------------------------------------------------------------------
KEEP_TILES=false
for arg in "$@"; do
    case "$arg" in
        --keep-tiles) KEEP_TILES=true ;;
        *) echo "ERROR: unknown argument '$arg'" >&2; exit 2 ;;
    esac
done

# --- Paths --------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ASSETS_DIR="$BACKEND_DIR/map-assets"
DATA_DIR="$BACKEND_DIR/data"
TILES_DIR="$BACKEND_DIR/tiles"
BUNDLE_DIR="$DATA_DIR/map-bundle"
BUNDLE_ZIP="$DATA_DIR/map-bundle.zip"
CACHE_DIR="$BACKEND_DIR/.cache/planetiler"
JAR="$CACHE_DIR/planetiler-${PLANETILER_VERSION}.jar"

# --- Preflight: tools ---------------------------------------------------------
for cmd in java jq curl zip shasum python3; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: '$cmd' is required but not installed." >&2
        exit 1
    fi
done

# --- Preflight: Java >= 21 ----------------------------------------------------
# On macOS, /usr/bin/java is a stub present even with no JDK installed, so the
# `command -v java` check above passes; invoking it then fails. Probe inside an
# `if` so a non-runnable java surfaces a clear error instead of `set -e`/pipefail
# aborting the script silently (this runs before the cleanup trap is installed).
if ! java_version_output=$(java -version 2>&1); then
    echo "ERROR: 'java' is present but not runnable — no JDK installed?" >&2
    echo "       Planetiler $PLANETILER_VERSION needs Java >= $JAVA_MIN_MAJOR." >&2
    echo "       Install e.g. 'brew install openjdk@21' and ensure 'java' is on PATH." >&2
    echo "       Reported by java: ${java_version_output:-<no output>}" >&2
    exit 1
fi
JAVA_MAJOR=$(printf '%s\n' "$java_version_output" | head -1 | sed -E 's/.*version "([0-9]+).*/\1/')
if ! [[ "$JAVA_MAJOR" =~ ^[0-9]+$ ]] || [ "$JAVA_MAJOR" -lt "$JAVA_MIN_MAJOR" ]; then
    echo "ERROR: Planetiler $PLANETILER_VERSION needs Java >= $JAVA_MIN_MAJOR; found '$JAVA_MAJOR'." >&2
    echo "       Install e.g. 'brew install openjdk@21' and ensure 'java' is on PATH." >&2
    exit 1
fi

# --- Preflight: vendored static assets ----------------------------------------
if [ ! -f "$ASSETS_DIR/style-template.json" ]; then
    echo "ERROR: $ASSETS_DIR/style-template.json not found." >&2
    exit 1
fi
if [ -z "$(find "$ASSETS_DIR/fonts" -name '*.pbf' -print -quit 2>/dev/null)" ]; then
    echo "ERROR: no glyph PBFs under $ASSETS_DIR/fonts." >&2
    exit 1
fi

# --- Ensure pinned Planetiler jar (cached, sha256-verified) -------------------
verify_jar() {
    [ -f "$1" ] || return 1
    [ "$(shasum -a 256 "$1" | awk '{print $1}')" = "$PLANETILER_SHA256" ]
}
mkdir -p "$CACHE_DIR"
if verify_jar "$JAR"; then
    echo "Using cached Planetiler $PLANETILER_VERSION."
else
    echo "Downloading Planetiler $PLANETILER_VERSION..."
    tmpjar="$CACHE_DIR/.planetiler-${PLANETILER_VERSION}.jar.tmp"
    rm -f "$tmpjar"
    curl -fL --retry 3 -o "$tmpjar" "$PLANETILER_URL"
    got=$(shasum -a 256 "$tmpjar" | awk '{print $1}')
    if [ "$got" != "$PLANETILER_SHA256" ]; then
        rm -f "$tmpjar"
        echo "ERROR: Planetiler jar sha256 mismatch." >&2
        echo "       got:  $got" >&2
        echo "       want: $PLANETILER_SHA256" >&2
        exit 1
    fi
    mv "$tmpjar" "$JAR"
fi

# --- Scratch dir + cleanup trap (leaves only the bundle) ----------------------
SCRATCH="$(mktemp -d)"
cleanup() {
    rc=$?
    rm -rf "$SCRATCH"
    trap - EXIT
    exit $rc
}
trap cleanup EXIT INT TERM

# --- Generate tiles (Planetiler) ----------------------------------------------
# maxzoom=12: keeps street-level detail but drops z13+ so the mbtiles fits inside
# a plain APK/AAB (no Play Asset Delivery). Bulgaria fits in a single z5 tile so a
# higher minzoom buys nothing. --nodemap-storage=mmap keeps the heap bounded.
echo "Generating Bulgaria tiles with Planetiler (downloads ~200 MB OSM extract)..."
java -Xmx4g -jar "$JAR" \
    --download --force --area=bulgaria \
    --minzoom=5 --maxzoom=12 \
    --output="$SCRATCH/bulgaria.mbtiles" \
    --tmpdir="$SCRATCH/tmp" \
    --download-dir="$SCRATCH/sources" \
    --nodemap-storage=mmap

if [ ! -f "$SCRATCH/bulgaria.mbtiles" ]; then
    echo "ERROR: Planetiler did not produce bulgaria.mbtiles." >&2
    exit 1
fi

# --- Assemble the bundle ------------------------------------------------------
rm -rf "$BUNDLE_DIR" "$BUNDLE_ZIP"
mkdir -p "$BUNDLE_DIR"

echo "Staging light style..."
cp "$ASSETS_DIR/style-template.json" "$BUNDLE_DIR/style-light.json"

echo "Deriving dark variant (style-dark.json)..."
python3 "$SCRIPT_DIR/derive-dark-style.py" \
    --in "$BUNDLE_DIR/style-light.json" \
    --out "$BUNDLE_DIR/style-dark.json"

echo "Staging glyphs..."
cp -R "$ASSETS_DIR/fonts" "$BUNDLE_DIR/fonts"
# Sprites: basic-preview declares none. If a sprite/ dir is ever vendored, stage it.
if [ -d "$ASSETS_DIR/sprite" ]; then
    cp -R "$ASSETS_DIR/sprite" "$BUNDLE_DIR/sprite"
fi

echo "Copying generated mbtiles..."
cp "$SCRATCH/bulgaria.mbtiles" "$BUNDLE_DIR/bulgaria.mbtiles"

# Drop stray Finder metadata so the zip stays clean (the hash ignores it anyway).
find "$BUNDLE_DIR" -name .DS_Store -delete

# --- Deterministic content hash -----------------------------------------------
echo "Computing deterministic map_hash..."
BUNDLE_HASH=$(python3 "$SCRIPT_DIR/compute-map-hash.py" "$BUNDLE_DIR")
BUNDLE_VERSION=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "$BUNDLE_DIR/version.json" <<EOF
{
  "version": "$BUNDLE_VERSION",
  "map_hash": "$BUNDLE_HASH"
}
EOF

# --- Zip for distribution -----------------------------------------------------
echo "Zipping bundle..."
(cd "$BUNDLE_DIR" && zip -r -q "$BUNDLE_ZIP" . -x '*.DS_Store')

# --- Patch the served /api/version (if present) -------------------------------
VERSION_FILE="$DATA_DIR/version.json"
if [ -f "$VERSION_FILE" ]; then
    echo "Updating $VERSION_FILE with map_hash..."
    tmp=$(mktemp)
    jq --arg h "$BUNDLE_HASH" '.map_hash = $h' "$VERSION_FILE" > "$tmp"
    mv "$tmp" "$VERSION_FILE"
fi

# --- Optional: keep a standalone mbtiles copy (inspection / other tooling) ----
if [ "$KEEP_TILES" = true ]; then
    mkdir -p "$TILES_DIR"
    cp "$BUNDLE_DIR/bulgaria.mbtiles" "$TILES_DIR/bulgaria.mbtiles"
    echo "Kept tiles at $TILES_DIR/bulgaria.mbtiles (--keep-tiles)."
fi

BUNDLE_SIZE=$(ls -lh "$BUNDLE_ZIP" | awk '{print $5}')
echo ""
echo "Done."
echo "  Bundle dir: $BUNDLE_DIR"
echo "  Bundle zip: $BUNDLE_ZIP ($BUNDLE_SIZE)"
echo "  map_hash:   $BUNDLE_HASH"
