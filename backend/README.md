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

`data/zones.json` is the **single source of truth** both apps bundle at build
time (committed, byte-identical to `scrapers/data/zones.json`). Refresh it from a
fresh scrape with the canonical helper:

```bash
bash ../scrapers/scripts/refresh-zones.sh   # scrape -> scrapers/data/ + sync backend/data/
```

`scripts/update-zones.sh` is a lighter local-inspection alternative — it copies a
generated `zones.json` into `data/` and writes a matching `data/version.json`. The
live `/api/*` metadata is produced by the scraper cron, not from here.

## Layout

- `scripts/build-map-bundle.sh` — the offline map-bundle builder (above).
- `scripts/compute-map-hash.py` — deterministic content hash for `map_hash`.
- `scripts/derive-dark-style.py` — derives `style-dark.json` from the light style.
- `scripts/update-zones.sh` — stage `zones.json` + `version.json` into `data/`.
- `map-assets/` — vendored static style template + Noto Sans glyphs (build inputs).
- `data/` — committed `zones.json` (single source of truth) + staged `version.json`; gitignored map-bundle output (`map-bundle/`, `map-bundle.zip`).
- `tiles/` — only used if you pass `--keep-tiles` (a standalone mbtiles copy); gitignored.
