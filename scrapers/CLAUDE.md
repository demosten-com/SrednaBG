# scrapers/

Python data pipeline (BeautifulSoup, requests, overpy) that scrapes zone data from 3 sources and produces `zones.json` (72 zones). Merges overlapping zones (prefer TollTracker coords, BG TOLL official status, OSM centerlines). Pydantic schema validation. 12 source files + 12 test files. `scripts/make_test_route.py` (stdlib-only) generates GPX drive-throughs from zone centerlines for emulator testing.

**Shared modules** — `src/geo.py` (haversine/bearing/polyline length), `src/roads.py` (road aliases, slugs, km-direction table, dominant-axis table, direction inference, `to_latin` BDS Cyrillic→Latin transliteration), `src/fetch.py` (retrying HTTP GET with backoff), `src/mvt.py` (pure-stdlib Mapbox Vector Tile decoder + slippy-tile math for the TollTracker fetcher; its write-side counterpart for tests is `tests/mvt_encoding.py`). These are the *only* copies; the per-scraper duplicates were removed after the tables drifted apart and shipped opposite-carriageway labels on I-1/I-3/I-5/II-55. Direction labels are geographic truth — lat increasing = north, lng increasing = east — and `roads.ROAD_AXIS` stores only the axis, so a per-road label inversion is not expressible. (АМ Европа's enforced section is the E-W Severna Tangenta, so its zones are east/west, axis `lng`, km increasing eastward.)

**Merge orientation reconciliation** (`validator._orient_to`, run inside `merge_match`): sources may list the same physical carriageway with opposite endpoint order, and the matcher accepts reversed pairs — so before per-endpoint fields are merged, every secondary source is reoriented to the primary (geometric endpoint comparison when both have coords; settlement-name orientation, then km-order vs `ROAD_DIRECTIONS`, for the coordinate-less BG TOLL). Without this, a reverse-matched pair crosses settlements/km markers onto the opposite carriageway's geometry — 21 shipped sections had swapped Latin/Cyrillic names and end-attached km markers before the fix. The matcher itself is junction-safe: `_km_ranges_overlap` requires ≥50% overlap of the shorter range (consecutive zones *touch* at a shared camera and must not match) and `_coords_close` requires both endpoints to coincide.

**Source failure = run failure** (`output.SourceFailure`): each active source scraper (`bgtoll`, `tolltracker`, `kml`) *raises* on fetch/parse failure (only per-item parse errors are skipped), and `run_pipeline` treats an exception **or an empty result** from any source as fatal — after attempting every source, it raises `SourceFailure` listing all of them, and `main()` exits 1 without writing (existing files untouched). Publishing with a source missing would silently degrade the data (the 2026-07 TollTracker redesign shipped a refresh that lost coordinates + Latin names on all 72 zones this way). `main()` re-logs the concise per-source errors *last*, so the Telegram failure message — which tails the final 30 lines of `cron.log` — always shows exactly what broke.

**Publish guard** (`output.publish_guard_errors`, enforced in `main()` for both `--output` and `--target-dir`): second net behind `SourceFailure`, against *partial* collapse that per-source failure detection can't see (a source quietly losing most of its zones) — refuses to write (exit 1, existing files untouched) when fewer than `MIN_PUBLISH_ZONES` (50) zones, any required motorway missing, or (target-dir mode) the count dropping below 70% of the served `version.json` `zone_count`.

**Geometry alignment** (`validator.align_centerline_to_endpoints`, run inside `merge_all`): the OSM centerline and the BG TOLL/TollTracker `start`/`end` endpoints come from different sources, so a raw centerline can stop short of the markers and `distance_m` can disagree with the arc length. The aligner canonicalises travel order start→end, then snaps a near-coincident terminal onto its endpoint (≤5 m) or inserts the endpoint as a new terminal point (larger gaps, preserving the OSM shape), and sets `distance_m` to the resulting arc length — so the drawn line connects both markers and the progress bar reaches 0 at the end. Gaps >150 m (the motorway road-width band) are still aligned but **warned** (likely bad upstream data). Idempotent; schema is unchanged (only coordinate/`distance_m` *values* move), so released clients keep parsing it. `validate()` then re-asserts each centerline is start-first as a post-condition guard, plus four consistency invariants (warnings): Latin names must transliterate their Cyrillic settlements, km markers must run the way `ROAD_DIRECTIONS` says for the zone's direction, `description` must equal "start – end", and same-road/direction junction seams must coincide (gap outside the 10–500 m ambiguous band). `tests/test_data_sanity.py` holds the *committed* `data/zones.json` to the same invariants (and to byte-parity with `backend/data/zones.json`), so a bad refresh fails CI instead of shipping. The engine self-orients centerlines at runtime too, so this realignment is belt-and-suspenders — it makes the *shipped* data correct, the engine guards against a future regression. `--realign <file>` re-applies it to an existing `zones.json` deterministically without a re-scrape (used to retrofit the bundled snapshot; `zones.json` was re-realigned this way).

`backend/data/zones.json` is the single source of truth both apps bundle at build time — iOS via its `Bundled Zones` Run Script phase, Android via the `prepareZonesAsset` Gradle task (Android's `src/main/assets/zones.json` is generated + gitignored, NOT committed, so the two platforms can't ship different zone data for the same release). The two committed copies — `scrapers/data/` (scraper output) and `backend/data/` (build source) — stay byte-identical; refresh both with `bash scrapers/scripts/refresh-zones.sh` (full scrape → `scrapers/data/zones.json`, then `cp` → `backend/data/zones.json`). The top-level `version` field is the scrape timestamp (ISO-8601 UTC, from `ZoneDatabase.now_version()`); the Android build reads it for a freshness WARNING when the bundled data is older than 10 days.

## Data sources

| Source | URL | Notes |
|--------|-----|-------|
| BG TOLL (official) | bgtoll.bg/vaprosi-i-otgovori | HTML tables, authoritative but no GPS coords |
| BG TOLL KML | google.com/maps/d/kml?mid=… (`kml_scraper.KML_URL`) | Google My Maps KMZ: centerlines, per-category limits, camera km markers |
| TollTracker.eu | tolltracker.eu/map | Mapbox vector tileset (`trackertech.tt-map-data`, public `pk.` token), best GPS coordinates |
| OSM Overpass | overpass-api.de/api/interpreter | `enforcement=average_speed` relations, currently none for BG. **Disabled in `run_pipeline()`** (commented out — the API answers 406 and contributes nothing); the module and its tests remain |

Zone data and BG TOLL scraping are Bulgarian Cyrillic.

**TollTracker vector-tile fetcher** (`tolltracker_fetcher.py`, since the site's 2026-07 redesign removed the RSC-embedded GeoJSON): discovers the Mapbox token + tileset id from the site's JS chunks at runtime (breadth-first over chunk references — the config sits in a dynamically-imported chunk — with hardcoded fallbacks), sweeps Bulgaria at z8 for `polylines` features with `type=section_control` / `country=BG`, then re-fetches each feature at detail zoom, stitching the per-tile clipped pieces into one centerline (`stitch_pieces`; clip-buffer overlap makes seams exact-vertex joins). The tileset is missing occasional high-zoom tiles, so each feature walks the `DETAIL_ZOOMS` ladder (12→11→10→8) until the stitched arc matches the feature's declared `length` within 10%. Tile features are **per-direction** (no fwd/rev synthesis), geometry runs in the title's travel order ("Вакарел - Ихтиман, Тракия" — verified against the old payload; `start_road_heading` is only trusted as a reversal check on one-way carriageways, on two-way roads it's the OSM way's canonical heading), carry a single `speed_limit` (so `SpeedLimits.truck/bus` became optional at source level — KML still outranks TollTracker for limits in the merge, and `validate()` warns if a *merged* zone lacks any of car/truck/bus), and no Latin names — `settlement_latin`/`road_latin` are synthesized from the Cyrillic title via `roads.to_latin`. Consecutive same-direction zones' shared-camera endpoints can disagree by a few metres across sources/tiles; `validator.snap_junction_seams` (run in `merge_all` before alignment, TollTracker-backed endpoint wins) snaps gaps ≤30 m so the junction-seam invariant holds.

## Build commands

```bash
# First-time env setup (single root .venv: scraper + dev + QA deps). The direct
# `python …` lines below assume it's active. The refresh-zones.sh wrapper and the
# `python -m src.output` entry point self-handle it — they auto-use the .venv if
# present, else tell you to run setup-python.sh.
bash ../scripts/setup-python.sh && source ../.venv/bin/activate

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
