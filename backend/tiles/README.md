# Tiles

Normally empty. The offline map bundle does **not** read from here —
`../scripts/build-map-bundle.sh` generates the tiles in a scratch dir and packs
them directly. This directory only receives a `bulgaria.mbtiles` if you pass
`--keep-tiles` (a standalone copy for inspection or other tooling); it's gitignored.

```bash
../scripts/build-map-bundle.sh --keep-tiles   # run from backend/scripts/ or via full path
```

That runs [Planetiler](https://github.com/onthegomap/planetiler) (pinned JAR)
against the Geofabrik Bulgaria OSM extract and writes `bulgaria.mbtiles` at
z5–z12 (~50 MB), OpenMapTiles schema.

## Expected file

- **Filename:** `bulgaria.mbtiles`
- **Format:** MBTiles (SQLite + vector tile data, OpenMapTiles schema)
- **Coverage:** All of Bulgaria, z5–z12
- **License:** © OpenStreetMap contributors (ODbL) — attribution required
  anywhere these tiles are surfaced.
