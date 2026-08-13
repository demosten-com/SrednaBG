# backend/

Build-time tooling for the offline map bundle the apps ship — a single self-contained script needing only Java + standard CLI tools. No services to run; the apps are offline-first and the production zone API is served by the scraper cron on the Namecheap shared host (see `scrapers/CLAUDE.md` "Hosted deployment"). The former Docker Compose serving stack (tileserver-gl + nginx) and `download-tiles.sh` are retired.

Scripts:
- `build-map-bundle.sh` — self-contained: downloads the pinned Planetiler JAR + Geofabrik Bulgaria OSM, generates z5–z12 tiles, packs the bundle from the in-repo `map-assets/`, cleans all scratch. `--keep-tiles` also drops a standalone mbtiles in `tiles/`.
- `compute-map-hash.py` — deterministic content hash for `map_hash` (see below).
- `derive-dark-style.py` — derives `style-dark.json` from the light style.
- `fetch-fdroid-map-bundle.sh` — F-Droid prebuild fetch+verify of `map-bundle-<tag>.zip` from the GitHub Release (tag derived from `versionName`, digest read from `web/fdroid/map-bundle-checksums.txt` — no per-release edit).
- `update-zones.sh` — local-inspection helper that stages `scrapers/data/zones.json` → `data/` + writes a `version.json`. Stages **every data feed** it finds beside the source (`zones.json` = feed 1, plus any `zones.N.json`), since each app bundles the file matching the feed it was compiled against — see `scrapers/CLAUDE.md` "Data feeds". Not the release path: `bash scrapers/scripts/refresh-zones.sh` is the canonical refresh, syncing the scraper output into `backend/data/zones.json`.
- `map-assets/` — vendored static style template + Noto Sans glyph PBFs (the build's inputs; see `map-assets/LICENSE-NOTES.md`).

`backend/data/zones.json` is the **single source of truth** both apps bundle at build time (iOS `Bundled Zones` phase, Android `prepareZonesAsset` task); it is committed, byte-identical to `scrapers/data/zones.json`. The map bundle below is independent of zone data.

## Build commands

```bash
bash backend/scripts/build-map-bundle.sh # Self-contained offline map bundle (Java 21+)
bash backend/scripts/update-zones.sh     # Stage zones.json + version.json into data/
```

## Offline map bundle (build step)

Fully self-contained MapLibre style + MBTiles + glyphs so the phone UI works without network. This folder is the canonical producer — Android and iOS each have their own staging/install/sync steps documented in their respective `CLAUDE.md`.

**Key split:** only `bulgaria.mbtiles` changes between map updates. The style + glyphs are static, vendored once in `backend/map-assets/`, so the build needs no tile server. `build-map-bundle.sh`:

1. Ensures the pinned Planetiler JAR (sha256-verified, cached in gitignored `backend/.cache/`) and generates `bulgaria.mbtiles` (z5–z12) in a scratch dir via `java -jar` — no Docker.
2. Copies `map-assets/style-template.json` → `style-light.json` (already carries `{MBTILES_URI}` / `{GLYPHS_URI}` placeholders) and derives `style-dark.json` (runtime picks one per the map-theme setting); copies the vendored `fonts/`.
3. Computes a **deterministic `map_hash`** via `compute-map-hash.py` (hashes the static files + the *decompressed* mbtiles tile rows ordered by z/x/y; excludes the mbtiles `metadata` table so unchanged content yields the same hash); writes `version.json`.
4. Outputs `backend/data/map-bundle/` + `map-bundle.zip`; patches `/api/version` with the new `map_hash`. A `trap` removes all scratch (OSM extract, Planetiler tmp, scratch mbtiles) on exit — only the bundle + zip remain.

This `map_hash` is the runtime sync change-detector and is distinct from the zip checksum that `web/fdroid/scripts/publish-map-bundle.sh` pins in `map-bundle-checksums.txt` (a single current-bundle digest, updated only when the map is rebuilt; the zip is not byte-reproducible, so it changes on every rebuild).

`/api/version` response carries `hash` (zones), `map_hash` (bundle), `zone_count`, and `feed`; each hash gates its own re-fetch on the client.

Design choice: map bundle ships inside the APK / iOS app bundle (mbtiles capped at z12), **not** via Play Asset Delivery — keeps F-Droid / sideload open.
