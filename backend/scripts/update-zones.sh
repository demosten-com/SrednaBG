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
# Every data feed the scraper wrote is staged, not just feed 1: `zones.json`
# (feed 1, the name every published install fetches) plus any `zones.N.json`
# beside it. Each app bundles the file matching the feed it was compiled
# against, so a feed missing here is a build that silently falls back to
# somebody else's data.
#
# Usage:
#   ./update-zones.sh [path/to/zones.json]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/../data"
REPO_ROOT="$SCRIPT_DIR/../.."

ZONES_SOURCE="${1:-$REPO_ROOT/scrapers/data/zones.json}"

if [ ! -f "$ZONES_SOURCE" ]; then
    echo "ERROR: zones.json not found at $ZONES_SOURCE"
    echo ""
    echo "Generate it first:"
    echo "  cd scrapers && python -m src.output"
    exit 1
fi

mkdir -p "$DATA_DIR"

# Stage every feed found beside the given zones.json, and generate each one's
# version.json from the data itself (fails loudly on malformed JSON).
python3 - "$ZONES_SOURCE" "$DATA_DIR" << 'PY'
import json
import re
import shutil
import sys
from pathlib import Path

source, dest_dir = Path(sys.argv[1]), Path(sys.argv[2])

# Feed 1 is the unsuffixed pair; feed N is `zones.N.json` / `version.N.json`.
# Mirrors scrapers/src/feeds.py — the one place that rule is allowed to live.
feeds = [(1, source)] + sorted(
    (int(m.group(1)), p)
    for p in source.parent.glob("zones.[0-9]*.json")
    if (m := re.fullmatch(r"zones\.([0-9]+)\.json", p.name))
)

for feed, zones_src in feeds:
    suffix = "" if feed == 1 else f".{feed}"
    zones_dest = dest_dir / f"zones{suffix}.json"
    version_dest = dest_dir / f"version{suffix}.json"

    shutil.copyfile(zones_src, zones_dest)
    print(f"Copied {zones_src.name} to {zones_dest}")

    with open(zones_dest, encoding="utf-8") as f:
        db = json.load(f)
    try:
        with open(version_dest, encoding="utf-8") as f:
            prev_map_hash = json.load(f).get("map_hash")
    except (OSError, ValueError):
        prev_map_hash = None
    meta = {
        "version": db["version"],
        "hash": db["hash"],
        "feed": feed,
        "min_app_version": "1.0.0",
        "zone_count": len(db["zones"]),
        "map_hash": prev_map_hash,
    }
    with open(version_dest, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    print(f"Generated {version_dest.name}:")
    print(json.dumps(meta, indent=2))
PY
