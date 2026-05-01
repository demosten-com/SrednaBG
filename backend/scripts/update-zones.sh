#!/usr/bin/env bash
# Update zone data from scrapers output.
#
# Copies scrapers/data/zones.json to the nginx serving directory
# and generates a version.json metadata file.
#
# Usage:
#   ./update-zones.sh [path/to/zones.json]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/../data"
REPO_ROOT="$SCRIPT_DIR/../.."

ZONES_SOURCE="${1:-$REPO_ROOT/scrapers/data/zones.json}"
ZONES_DEST="$DATA_DIR/zones.json"
VERSION_DEST="$DATA_DIR/version.json"

if [ ! -f "$ZONES_SOURCE" ]; then
    echo "ERROR: zones.json not found at $ZONES_SOURCE"
    echo ""
    echo "Generate it first:"
    echo "  cd scrapers && python -m src.output"
    exit 1
fi

mkdir -p "$DATA_DIR"

# Copy zones.json
cp "$ZONES_SOURCE" "$ZONES_DEST"
echo "Copied zones.json to $ZONES_DEST"

# Generate version.json
VERSION=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
HASH=$(shasum -a 256 "$ZONES_DEST" | cut -d' ' -f1)
ZONE_COUNT=$(python3 -c "import json; print(len(json.load(open('$ZONES_DEST'))['zones']))" 2>/dev/null || echo "0")

cat > "$VERSION_DEST" << EOF
{
  "version": "$VERSION",
  "hash": "sha256:$HASH",
  "min_app_version": "1.0.0",
  "zone_count": $ZONE_COUNT
}
EOF

echo "Generated version.json:"
cat "$VERSION_DEST"
