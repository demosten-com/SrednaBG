#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — backend / scripts

"""Derive a dark MapLibre style from the bundled light basic-preview style.

Reads a JSON style document and writes a dark-themed variant that keeps every
layer, filter, layout, and zoom stop intact and only rewrites color values in
known paint properties. The light style is the source of truth — re-running
this script regenerates the dark variant.

Usage:
    derive-dark-style.py --in <light.json> --out <dark.json>
"""

import argparse
import json


# Per-layer paint overrides for a dark night-style palette.
# Ids match `basic-preview`'s OpenMapTiles schema (see `backend/data/map-bundle/style.json`).
LAYER_OVERRIDES = {
    "background": {"background-color": "hsl(220, 14%, 11%)"},
    "landuse-residential": {"fill-color": "hsl(220, 12%, 14%)"},
    "landcover_grass": {"fill-color": "hsl(120, 18%, 16%)"},
    "landcover_wood": {"fill-color": "hsl(120, 20%, 14%)"},
    "water": {"fill-color": "hsl(210, 45%, 18%)"},
    "water_intermittent": {"fill-color": "hsl(210, 45%, 18%)"},
    "landcover-ice-shelf": {"fill-color": "hsl(220, 8%, 18%)"},
    "landcover-glacier": {"fill-color": "hsl(220, 6%, 22%)"},
    "landcover_sand": {"fill-color": "rgba(180, 160, 60, 0.18)"},
    "landuse": {"fill-color": "#2a2826"},
    "landuse_overlay_national_park": {"fill-color": "#1d2a1d"},
    "waterway-tunnel": {"line-color": "hsl(210, 45%, 22%)"},
    "waterway": {"line-color": "hsl(210, 45%, 28%)"},
    "waterway_intermittent": {"line-color": "hsl(210, 45%, 28%)"},
    "tunnel_railway_transit": {"line-color": "hsl(34, 8%, 30%)"},
    "building": {
        "fill-color": "rgba(38, 41, 46, 1)",
        "fill-outline-color": {
            "stops": [[15, "rgba(70, 72, 78, 0)"], [16, "rgba(70, 72, 78, 0.5)"]]
        },
    },
    "housenumber": {"text-color": "rgba(160, 164, 170, 1)"},
    "road_area_pier": {"fill-color": "hsl(220, 12%, 14%)"},
    "road_pier": {"line-color": "hsl(220, 12%, 14%)"},
    "road_bridge_area": {"fill-color": "hsl(220, 12%, 14%)"},
    "road_path": {"line-color": "hsl(0, 0%, 50%)"},
    "road_minor": {"line-color": "hsl(0, 0%, 38%)"},
    "tunnel_minor": {"line-color": "#3c3f44"},
    "tunnel_major": {"line-color": "#4a4d52"},
    "aeroway-area": {"fill-color": "rgba(60, 62, 66, 1)"},
    "aeroway-taxiway": {"line-color": "rgba(60, 62, 66, 1)"},
    "aeroway-runway": {"line-color": "rgba(70, 72, 76, 1)"},
    "road_trunk_primary": {"line-color": "#5a5e64"},
    "road_secondary_tertiary": {"line-color": "#4a4e54"},
    "road_major_motorway": {"line-color": "hsl(0, 0%, 38%)"},
    "railway-transit": {"line-color": "hsl(34, 6%, 28%)"},
    "railway": {"line-color": "hsl(34, 6%, 28%)"},
    "waterway-bridge-case": {"line-color": "#404348"},
    "waterway-bridge": {"line-color": "hsl(210, 45%, 28%)"},
    "bridge_minor case": {"line-color": "#404348"},
    "bridge_major case": {"line-color": "#404348"},
    "bridge_minor": {"line-color": "#3c3f44"},
    "bridge_major": {"line-color": "#5a5e64"},
    "admin_sub": {"line-color": "hsla(0, 0%, 50%, 0.5)"},
    "admin_country": {"line-color": "hsl(0, 0%, 60%)"},
    "poi_label": {
        "text-color": "#A0A4AA",
        "text-halo-color": "rgba(0, 0, 0, 0.6)",
    },
    "airport-label": {
        "text-color": "#A0A4AA",
        "text-halo-color": "rgba(0, 0, 0, 0.6)",
    },
    "road_major_label": {
        "text-color": "#E8EAED",
        "text-halo-color": "rgba(0, 0, 0, 0.7)",
    },
    "place_label_other": {
        "text-color": "hsl(0, 0%, 80%)",
        "text-halo-color": "rgba(0, 0, 0, 0.6)",
    },
    "place_label_city": {
        "text-color": "hsl(0, 0%, 92%)",
        "text-halo-color": "rgba(0, 0, 0, 0.65)",
    },
    "country_label-other": {
        "text-color": "hsl(0, 0%, 88%)",
        "text-halo-color": "rgba(0, 0, 0, 0.65)",
    },
    "country_label": {
        "text-color": "hsl(0, 0%, 88%)",
        "text-halo-color": "rgba(0, 0, 0, 0.65)",
    },
}


def patch_paint(layer):
    overrides = LAYER_OVERRIDES.get(layer.get("id"))
    if not overrides:
        return
    paint = layer.setdefault("paint", {})
    for prop, value in overrides.items():
        paint[prop] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="src", required=True, help="Path to the light style.json")
    parser.add_argument("--out", dest="dst", required=True, help="Path to write the dark style.json")
    args = parser.parse_args()

    with open(args.src, "r", encoding="utf-8") as f:
        style = json.load(f)

    style["name"] = "Basic preview (dark)"
    style["id"] = "basic-preview-dark"
    if "metadata" not in style:
        style["metadata"] = {}

    for layer in style.get("layers", []):
        patch_paint(layer)

    with open(args.dst, "w", encoding="utf-8") as f:
        json.dump(style, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
