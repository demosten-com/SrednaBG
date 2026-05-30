# SrednaBG Backend

Build-time tooling for the **offline map bundle** that ships inside the Android
APK and iOS app, plus a small helper for staging zone data locally. No services
to run — the apps are offline-first, and the production zone API (`/api/zones`,
`/api/version`) is served by the scraper cron on the Namecheap shared host (see
`scrapers/CLAUDE.md` "Hosted deployment" and `web/CLAUDE.md`).

## Prerequisites

- `java` (>=21), `jq`, `curl`, `zip`, `shasum`, `python3`.
- ~4 GB free RAM + ~2 GB scratch disk for tile generation.

No Docker, no tile server.

## Quick Start

### 1. Build the offline map bundle

```bash
bash scripts/build-map-bundle.sh           # add --keep-tiles to also drop a standalone mbtiles in tiles/
```

Self-contained: downloads the pinned [Planetiler](https://github.com/onthegomap/planetiler)
JAR and, via Planetiler, the Geofabrik Bulgaria OSM extract (~200 MB); generates
the z5–z12 vector tiles; assembles the bundle from the in-repo static assets in
`map-assets/` (style + glyphs); derives the dark style; computes a deterministic
`map_hash` (`scripts/compute-map-hash.py`); and zips to `data/map-bundle.zip`.
All scratch data is removed on exit — only the bundle + zip remain. Android/iOS
builds stage `data/map-bundle/` automatically. Tile data © OpenStreetMap
contributors (ODbL); see `map-assets/LICENSE-NOTES.md`.

### 2. (Optional) Stage zone data locally

`scripts/update-zones.sh` copies a generated `zones.json` into `data/` and writes
a matching `data/version.json` — handy for local inspection. The live API is
produced by the scraper cron, not from here.

```bash
cd ../scrapers && python -m src.output    # regenerate zones.json
cd ../backend  && ./scripts/update-zones.sh
```

## Layout

- `scripts/build-map-bundle.sh` — the offline map-bundle builder (above).
- `scripts/compute-map-hash.py` — deterministic content hash for `map_hash`.
- `scripts/derive-dark-style.py` — derives `style-dark.json` from the light style.
- `scripts/update-zones.sh` — stage `zones.json` + `version.json` into `data/`.
- `map-assets/` — vendored static style template + Noto Sans glyphs (build inputs).
- `data/` — build output (`map-bundle/`, `map-bundle.zip`) + staged zone data; gitignored bundle.
- `tiles/` — only used if you pass `--keep-tiles` (a standalone mbtiles copy); gitignored.
