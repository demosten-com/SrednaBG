# backend/

Docker Compose config for Mac Mini M4 running tileserver-gl (Bulgaria OpenMapTiles) + nginx (zones API, tile proxy, map-bundle download). Self-hosted — no recurring cloud costs; 1 Gbit upload handles thousands of users.

Setup scripts:
- `download-tiles.sh` — Planetiler → capped at z5–z12 so mbtiles fit in the APK
- `build-map-bundle.sh` — fetches style/sprites/fonts from tileserver-gl, rewrites URIs to placeholders, zips with mbtiles
- `update-zones.sh`

## Build commands

```bash
bash backend/scripts/download-tiles.sh   # Planetiler → z5–z12 bulgaria.mbtiles
cd backend && docker compose up          # tileserver-gl + nginx
bash backend/scripts/build-map-bundle.sh # Offline map bundle (needs tileserver-gl running)
bash backend/scripts/update-zones.sh     # Refresh /api/version + zones payload
```

## Offline map bundle (build step)

Fully self-contained MapLibre style + MBTiles + glyphs + sprites so the phone UI works without network. This folder is the canonical producer — Android and iOS each have their own staging/install/sync steps documented in their respective `CLAUDE.md`.

`build-map-bundle.sh`:

1. Queries local tileserver-gl for `basic-preview` style/sprites/glyph PBFs (every fontstack referenced by symbol layers).
2. Rewrites the style's vector source to `{MBTILES_URI}` (plus `{GLYPHS_URI}` / `{SPRITE_URI}`).
3. Copies the shrunk `bulgaria.mbtiles`, records sha256 in `version.json`.
4. Outputs `backend/data/map-bundle/` + `map-bundle.zip`; patches `/api/version` with the new `map_hash`.

`/api/version` response carries `hash` (zones), `map_hash` (bundle), and `zone_count`; each hash gates its own re-fetch on the client.

Design choice: map bundle ships inside the APK / iOS app bundle (mbtiles capped at z12), **not** via Play Asset Delivery — keeps F-Droid / sideload open.
