# scrapers/

Python data pipeline (BeautifulSoup, requests, overpy) that scrapes zone data from 3 sources and produces `zones.json` (72 zones). Merges overlapping zones (prefer TollTracker coords, BG TOLL official status, OSM centerlines). Pydantic schema validation. 11 source files + 7 test files. `scripts/make_test_route.py` (stdlib-only) generates GPX drive-throughs from zone centerlines for emulator testing.

**Shared modules** — `src/geo.py` (haversine/bearing/polyline length), `src/roads.py` (road aliases, slugs, km-direction table, dominant-axis table, direction inference), `src/fetch.py` (retrying HTTP GET with backoff). These are the *only* copies; the per-scraper duplicates were removed after the tables drifted apart and shipped opposite-carriageway labels on I-1/I-3/I-5/II-55. Direction labels are geographic truth — lat increasing = north, lng increasing = east — and `roads.ROAD_AXIS` stores only the axis, so a per-road label inversion is not expressible. (АМ Европа's enforced section is the E-W Severna Tangenta, so its zones are east/west, axis `lng`, km increasing eastward.)

**Merge orientation reconciliation** (`validator._orient_to`, run inside `merge_match`): sources may list the same physical carriageway with opposite endpoint order, and the matcher accepts reversed pairs — so before per-endpoint fields are merged, every secondary source is reoriented to the primary (geometric endpoint comparison when both have coords; settlement-name orientation, then km-order vs `ROAD_DIRECTIONS`, for the coordinate-less BG TOLL). Without this, a reverse-matched pair crosses settlements/km markers onto the opposite carriageway's geometry — 21 shipped sections had swapped Latin/Cyrillic names and end-attached km markers before the fix. The matcher itself is junction-safe: `_km_ranges_overlap` requires ≥50% overlap of the shorter range (consecutive zones *touch* at a shared camera and must not match) and `_coords_close` requires both endpoints to coincide.

**Publish guard** (`output.publish_guard_errors`, enforced in `main()` for both `--output` and `--target-dir`): refuses to write (exit 1, existing files untouched) when the scrape collapses — fewer than `MIN_PUBLISH_ZONES` (50) zones, any required motorway missing, or (target-dir mode) the count dropping below 70% of the served `version.json` `zone_count`. Each scraper returns `[]` on failure by design, so without the guard a broken upstream would publish a near-empty zones.json to the live `/api/zones`.

**Geometry alignment** (`validator.align_centerline_to_endpoints`, run inside `merge_all`): the OSM centerline and the BG TOLL/TollTracker `start`/`end` endpoints come from different sources, so a raw centerline can stop short of the markers and `distance_m` can disagree with the arc length. The aligner canonicalises travel order start→end, then snaps a near-coincident terminal onto its endpoint (≤5 m) or inserts the endpoint as a new terminal point (larger gaps, preserving the OSM shape), and sets `distance_m` to the resulting arc length — so the drawn line connects both markers and the progress bar reaches 0 at the end. Gaps >150 m (the motorway road-width band) are still aligned but **warned** (likely bad upstream data). Idempotent; schema is unchanged (only coordinate/`distance_m` *values* move), so released clients keep parsing it. `validate()` then re-asserts each centerline is start-first as a post-condition guard, plus four consistency invariants (warnings): Latin names must transliterate their Cyrillic settlements, km markers must run the way `ROAD_DIRECTIONS` says for the zone's direction, `description` must equal "start – end", and same-road/direction junction seams must coincide (gap outside the 10–500 m ambiguous band). `tests/test_data_sanity.py` holds the *committed* `data/zones.json` to the same invariants (and to byte-parity with `backend/data/zones.json`), so a bad refresh fails CI instead of shipping. The engine self-orients centerlines at runtime too, so this realignment is belt-and-suspenders — it makes the *shipped* data correct, the engine guards against a future regression. `--realign <file>` re-applies it to an existing `zones.json` deterministically without a re-scrape (used to retrofit the bundled snapshot; `zones.json` was re-realigned this way).

`backend/data/zones.json` is the single source of truth both apps bundle at build time — iOS via its `Bundled Zones` Run Script phase, Android via the `prepareZonesAsset` Gradle task (Android's `src/main/assets/zones.json` is generated + gitignored, NOT committed, so the two platforms can't ship different zone data for the same release). The two committed copies — `scrapers/data/` (scraper output) and `backend/data/` (build source) — stay byte-identical; refresh both with `bash scrapers/scripts/refresh-zones.sh` (full scrape → `scrapers/data/zones.json`, then `cp` → `backend/data/zones.json`). The top-level `version` field is the scrape timestamp (ISO-8601 UTC, from `ZoneDatabase.now_version()`); the Android build reads it for a freshness WARNING when the bundled data is older than 10 days.

## Data sources

| Source | URL | Notes |
|--------|-----|-------|
| BG TOLL (official) | bgtoll.bg/vaprosi-i-otgovori | HTML tables, authoritative but no GPS coords |
| BG TOLL KML | google.com/maps/d/kml?mid=… (`kml_scraper.KML_URL`) | Google My Maps KMZ: centerlines, per-category limits, camera km markers |
| TollTracker.eu | tolltracker.eu/map | GeoJSON in the Next.js RSC payload, best GPS coordinates |
| OSM Overpass | overpass-api.de/api/interpreter | `enforcement=average_speed` relations, currently none for BG |

Zone data and BG TOLL scraping are Bulgarian Cyrillic.

## Build commands

```bash
python -m pytest                         # All tests
python -m pytest tests/test_validator.py # One file
bash scripts/refresh-zones.sh            # Refresh bundled data: full scrape -> scrapers/data/ + sync backend/data/ (use this before a release cut)
python -m src.output                     # Regenerate zones.json only (full scrape, scrapers/data/)
python -m src.output --realign data/zones.json   # Network-free: re-align geometry of an existing file in place
python scripts/make_test_route.py --out /tmp/route.gpx  # Emulator drive GPX
# make_test_route.py flags: --zone-id, --speed-kmh, --approach-km, --exit-km, --hz
# Default: trakiya-01-east @ 130 km/h, 1 Hz
```

CI: `.github/workflows/scraper.yml` is **PR validation only** (scrape + pytest on PRs touching `scrapers/**`, plus `workflow_dispatch`). The committed `zones.json` is a manually-refreshed snapshot — run `refresh-zones.sh` locally before a release cut.

## Hosted deployment (Namecheap)

Production scheduling lives on the Namecheap shared host that serves `srednabg.com`. Cron runs `scripts/run_cron.sh`, which calls `python -m src.output --target-dir $HOME/srednabg_com/api` and pings Telegram.

Layout on the cPanel user's `$HOME` (note: the addon-domain docroot is `srednabg_com/`, **not** `public_html/srednabg_com/`):

| Path | Purpose |
|------|---------|
| `~/srednabg-scraper/` | Private; rsync target for `scrapers/src/`, `requirements.txt`, `scripts/run_cron.sh`. Holds `venv/`, `logs/cron.log`, `state/last_hash`. |
| `~/.config/srednabg/scraper.env` | `chmod 600`. `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`. Never committed. |
| `~/srednabg_com/api/zones.json` | Live, atomically replaced. Served as `/api/zones`. |
| `~/srednabg_com/api/version.json` | Live, atomically replaced. Served as `/api/version`. `map_hash` is `null` until a map bundle is uploaded. |
| `~/srednabg_com/api/zones-<UTC-timestamp>.json` | Snapshot saved on every content change; newest 26 retained (~6 months at weekly cadence). |

`--target-dir` mode in `src/output.py` is the production entry point: it atomic-writes both files (`*.tmp` → `os.replace`) and snapshots the prior `zones.json` only when content changed. `--output` remains for one-shot local runs.

Cron entry (server-local time; pick a low-traffic hour and accept TZ drift since exact UTC alignment doesn't matter):

```cron
0 4 * * 1 /home/<cpanel_user>/srednabg-scraper/scripts/run_cron.sh
```

Telegram notify fires on every run — success message has zone count, hash, changed-yes/no, duration; failure message tails the last 30 lines of `cron.log`.

## Zone data schema

`/api/version` carries `hash` (zones), `map_hash` (bundle), and `zone_count`; each hash gates its own re-fetch on the client.

```json
{
  "version": "2026-04-12T10:00:00Z",
  "hash": "sha256:abc123...",
  "zones": [{
    "id": "trakiya-01-east", "road": "AM Trakiya (A1)", "direction": "east",
    "description": "Вакарел – Ихтиман",
    "start": { "lat": 42.5432, "lng": 23.8234, "km_marker": "24+288", "settlement": "Вакарел" },
    "end":   { "lat": 42.4321, "lng": 23.9876, "km_marker": "43+448", "settlement": "Ихтиман" },
    "distance_m": 19160,
    "speed_limits": { "car": 140, "truck": 90, "bus": 100 },
    "centerline": [[42.5432, 23.8234], [42.5400, 23.8300], [42.4321, 23.9876]],
    "source": "bgtoll+tolltracker", "last_verified": "2026-04-01"
  }]
}
```
