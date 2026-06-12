#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — backend / scripts

# Update zone data from scrapers output.
#
# Stages scrapers/data/zones.json into backend/data/ (local inspection copy)
# and generates a matching version.json metadata file. The metadata follows the
# production convention (scrapers/src/output.py write_target_dir): `version`
# and `hash` are the values embedded in zones.json — the canonical content hash
# that excludes volatile per-zone fields — not a raw digest of the file bytes.
# An existing map_hash (patched in by build-map-bundle.sh) is preserved.
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

# Generate version.json from the data itself (fails loudly on malformed JSON).
python3 - "$ZONES_DEST" "$VERSION_DEST" << 'PY'
import json
import sys

zones_path, version_path = sys.argv[1], sys.argv[2]
with open(zones_path, encoding="utf-8") as f:
    db = json.load(f)
try:
    with open(version_path, encoding="utf-8") as f:
        prev_map_hash = json.load(f).get("map_hash")
except (OSError, ValueError):
    prev_map_hash = None
meta = {
    "version": db["version"],
    "hash": db["hash"],
    "min_app_version": "1.0.0",
    "zone_count": len(db["zones"]),
    "map_hash": prev_map_hash,
}
with open(version_path, "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)
    f.write("\n")
PY

echo "Generated version.json:"
cat "$VERSION_DEST"
