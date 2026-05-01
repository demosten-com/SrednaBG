# Tiles

Place the Bulgaria OpenMapTiles `.mbtiles` file here as `bulgaria.mbtiles`.

## Download

1. Create a free account at [data.maptiler.com](https://data.maptiler.com/)
2. Download the Bulgaria extract (~200-300 MB):
   - Go to: https://data.maptiler.com/downloads/tileset/osm/europe/bulgaria/
   - Download the OpenMapTiles `.mbtiles` format
3. Place the file here as `bulgaria.mbtiles`

Or use the download script:
```bash
../scripts/download-tiles.sh YOUR_MAPTILER_KEY
```

## Expected File

- **Filename:** `bulgaria.mbtiles`
- **Size:** ~200-300 MB
- **Format:** MBTiles (SQLite with vector tile data)
- **Coverage:** All of Bulgaria

This file is gitignored (see root `.gitignore`).
