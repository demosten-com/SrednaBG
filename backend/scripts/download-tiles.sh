#!/usr/bin/env bash
# Generate Bulgaria OpenMapTiles .mbtiles for tileserver-gl
#
# Uses Planetiler (via Docker) to convert a Geofabrik Bulgaria OSM extract
# into an OpenMapTiles-schema mbtiles file. No API key needed.
#
# Prerequisites:
#   - Docker installed and running
#   - ~4 GB free RAM (for Planetiler JVM)
#   - ~1 GB free disk (PBF download + mbtiles output)
#
# Usage:
#   ./download-tiles.sh
#
# Data license: OpenStreetMap (ODbL) — attribute "OpenStreetMap contributors"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TILES_DIR="$SCRIPT_DIR/../tiles"
OUTPUT_FILE="$TILES_DIR/bulgaria.mbtiles"

mkdir -p "$TILES_DIR"

if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is required but not installed."
    echo "Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info &>/dev/null; then
    echo "ERROR: Docker is not running. Please start Docker and try again."
    exit 1
fi

echo "Generating Bulgaria OpenMapTiles with Planetiler..."
echo "  Output: $OUTPUT_FILE"
echo "  This will download the Bulgaria OSM extract from Geofabrik (~200 MB)"
echo "  and generate mbtiles locally. May take a few minutes."
echo ""

# maxzoom=12: street-level detail is still present but drops z13+z14,
# which slashes file size ~3-4x so the mbtiles fits inside a plain APK/AAB
# (no Play Asset Delivery). Bulgaria fits in a single z5 tile so higher
# minzoom buys nothing.
docker run --rm \
    -e JAVA_TOOL_OPTIONS="-Xmx4g" \
    -v "$TILES_DIR":/data \
    ghcr.io/onthegomap/planetiler:latest \
    --download --force --area=bulgaria \
    --minzoom=5 --maxzoom=12 \
    --mbtiles=/data/bulgaria.mbtiles

if [ -f "$OUTPUT_FILE" ]; then
    SIZE=$(ls -lh "$OUTPUT_FILE" | awk '{print $5}')
    echo ""
    echo "Done: $OUTPUT_FILE ($SIZE)"
    echo "Data: OpenStreetMap contributors (ODbL)"
else
    echo "ERROR: Generation failed. File not found at $OUTPUT_FILE"
    exit 1
fi
