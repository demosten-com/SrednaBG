# Tiles

`bulgaria.mbtiles` (Bulgaria OpenMapTiles, vector) lives here. The file is
gitignored — generate it locally before bringing up the docker compose
stack.

## Build

```bash
../scripts/download-tiles.sh    # run from backend/ (or call with the full path)
```

Runs [Planetiler](https://github.com/onthegomap/planetiler) in Docker against
the Geofabrik Bulgaria OSM extract. No API key needed. Output: `bulgaria.mbtiles`
at z5–z12 (~50 MB), the same shape tileserver-gl and the offline-bundle
builder consume.

## Expected file

- **Filename:** `bulgaria.mbtiles`
- **Format:** MBTiles (SQLite + vector tile data, OpenMapTiles schema)
- **Coverage:** All of Bulgaria, z5–z12
- **License:** © OpenStreetMap contributors (ODbL) — attribution required
  anywhere these tiles are surfaced.
