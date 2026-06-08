# scrapers/

Python data pipeline (BeautifulSoup, requests, overpy) that scrapes zone data from 3 sources and produces `zones.json`. Merges overlapping zones (prefer TollTracker coords, BG TOLL official status, OSM centerlines). Pydantic schema validation. 6 source files + 4 test files. `scripts/make_test_route.py` (stdlib-only) generates GPX drive-throughs from zone centerlines for emulator testing.

**Geometry alignment** (`validator.align_centerline_to_endpoints`, run inside `merge_all`): the OSM centerline and the BG TOLL/TollTracker `start`/`end` endpoints come from different sources, so a raw centerline can stop tens of metres short of the markers and `distance_m` (official) can disagree with the arc length. The aligner snaps a near-coincident terminal onto its endpoint (≤5 m) or inserts the endpoint as a new terminal point (larger gaps, preserving the OSM shape), then sets `distance_m` to the resulting arc length — so the drawn line connects both markers, the progress bar reaches 0 at the end, and the app's "past the end" checks are correct. Gaps >150 m (the motorway road-width band) are still aligned but **warned** (likely bad upstream data); within 150 m the terminal is still inside the road the detector matches against, so it's expected source slack. Schema is unchanged (only coordinate/`distance_m` *values* move), so already-released clients keep parsing it. `--realign <file>` re-applies this to an existing `zones.json` deterministically without a re-scrape (used to retrofit the bundled snapshot). The three committed copies — `scrapers/data/`, `backend/data/`, `android/app/src/main/assets/` — must stay byte-identical.

## Data sources

| Source | URL | Notes |
|--------|-----|-------|
| BG TOLL (official) | bgtoll.bg/vaprosi-i-otgovori/sredna-skorost | HTML tables, authoritative but no GPS coords |
| TollTracker.eu | tolltracker.eu/en/map | GeoJSON, best GPS coordinates |
| OSM Overpass | overpass-api.de/api/interpreter | `enforcement=average_speed` relations, may be incomplete |

Zone data and BG TOLL scraping are Bulgarian Cyrillic.

## Build commands

```bash
python -m pytest                         # All tests
python -m pytest tests/test_validator.py # One file
python -m src.output                     # Regenerate zones.json (full scrape)
python -m src.output --realign data/zones.json   # Network-free: re-align geometry of an existing file in place
python scripts/make_test_route.py --out /tmp/route.gpx  # Emulator drive GPX
# make_test_route.py flags: --zone-id, --speed-kmh, --approach-km, --exit-km, --hz
# Default: trakiya-01-east @ 130 km/h, 1 Hz
```

CI: `.github/workflows/scraper.yml` is **PR validation only** (scrape + pytest on PRs touching `scrapers/**`, plus `workflow_dispatch`). The repo's `scrapers/data/zones.json` is a manually-refreshed bundled-fallback snapshot — refresh it locally with `python -m src.output` before a release cut.

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
