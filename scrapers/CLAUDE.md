# scrapers/

Python data pipeline (BeautifulSoup, requests, overpy) that scrapes zone data from 3 sources and produces `zones.json` (74 zones). Merges overlapping zones (prefer TollTracker coords, BG TOLL official status, OSM centerlines). Pydantic schema validation. 12 source files + 12 test files. `scripts/make_test_route.py` (stdlib-only) generates GPX drive-throughs from zone centerlines for emulator testing.

**Shared modules** — `src/geo.py` (haversine/bearing/polyline length), `src/roads.py` (road aliases, slugs, km-direction table, dominant-axis table, direction inference, `to_latin` BDS Cyrillic→Latin transliteration), `src/fetch.py` (retrying HTTP GET with backoff), `src/mvt.py` (pure-stdlib Mapbox Vector Tile decoder + slippy-tile math for the TollTracker fetcher; its write-side counterpart for tests is `tests/mvt_encoding.py`). These are the *only* copies; the per-scraper duplicates were removed after the tables drifted apart and shipped opposite-carriageway labels on I-1/I-3/I-5/II-55. Direction labels are geographic truth — lat increasing = north, lng increasing = east — and `roads.ROAD_AXIS` stores only the axis, so a per-road label inversion is not expressible. (АМ Европа's enforced section is the E-W Severna Tangenta, so its zones are east/west, axis `lng`, km increasing eastward.)

**The BG TOLL KML is the authority.** `kml_scraper` reads BG TOLL's own published Google My Maps — the camera operator's map of its own cameras — so for every field the KML *authors*, its value is the source of truth and every other scraper is a secondary reading. `merge_match` ranks it first for **speed limits, road name, road type, centerline and distance**.

Two traps make this less obvious than it sounds.

**Trap 1 — two of our sources are BG TOLL, and only one of them carries limits.**

| BG TOLL source | Authors | Does NOT author |
|---|---|---|
| `kml_scraper` (Google My Maps export) | **per-category speed limits**, centerlines, camera placemarks, road id | settlements per endpoint, Latin names |
| `bgtoll_scraper` (FAQ HTML tables) | road name, km markers, settlements | **speed limits**, coordinates, geometry |

`bgtoll_scraper` scrapes **no limits at all** — every zone it emits carries `MOTORWAY_SPEED_LIMITS` / `NATIONAL_ROAD_SPEED_LIMITS`, our own statutory-maximum constants keyed on `is_motorway`. Ranking that tier above the KML would let a hardcoded assumption outrank the map it stands in for: on АМ Европа it publishes **140 where BG TOLL's own map says 120**, telling drivers to hold 20 km/h more than the camera allows (verified 2026-08-08 — the KML and TollTracker both say 120; only our constant says 140). Keep the `bgtoll` limits at the bottom of the hierarchy; they exist to fill a gap, not to lead.

**Only BG TOLL-backed zones ship** (`validator.drop_unofficial_zones`, run inside `merge_all` before IDs are assigned). A section BG TOLL publishes **nowhere** — neither in the FAQ tables nor on its own map — is one we have no authority for. TollTracker is a third party: it can be ahead of BG TOLL, but it can equally be wrong, and an app that announces an enforcement zone which does not exist is worse than one that stays quiet. Such zones are dropped with a per-zone warning rather than published.

Dropping rather than failing is deliberate, and the *aggregate* guards are what express "too inconsistent to ship": if the drops take the count under `MIN_PUBLISH_ZONES`, remove a required motorway, or collapse the count against what is currently served, `publish_guard_errors` refuses the whole publish. One unsupported zone must not freeze `/api` for everyone; a systematic collapse should. This is also what keeps the missing-limit case theoretical — a TollTracker-only zone is exactly the one that arrives with a `car` limit and nothing else (its tiles carry a single `speed_limit`), which is the payload that fails the entire iOS 1.x decode.

**Trap 2 — "authors" is doing real work.** Three fields are ranked away from the KML. None is a dispute about who is right on the facts; each is a field the KML does not author but merely derives, and each was measured before being kept (2026-08-08):

- **GPS coordinates** — TollTracker > KML > OSM. The KML's endpoints are just its centerline's terminals, and they are the coarser survey: adopting them broke **2 of the 24 shared-camera junction seams** (0 m → 110 m gap, past `snap_junction_seams`' 30 m tolerance) and raised backwards-jog openings from **20 to 29 zones** — the ISSUE-001 defect class that forced `START_WITNESS_ARC_M` to 200 m. BG TOLL publishes no coordinates anywhere, so nothing is being overruled; this is instrument precision, not authority.
- **Km markers** — BG TOLL > KML > TollTracker. The KML's are *inferred* by matching camera placemarks to endpoints (`_find_camera_km`); the FAQ tables state them outright.
- **Settlements** (and the `description` built from them) — BG TOLL > KML > TollTracker. The KML parses a single segment title ("Ихтиман-Мирово") and assigns the halves to endpoints by proximity, so they can cross. On I-8 they do — KML puts Мирово at the western end, contradicting both the km markers and the Latin names — and it misspells Горни Богров as "Горни Богоров". These strings are user-visible in both apps.

If you re-litigate any of these, re-run the measurement rather than reasoning from the principle: `refresh-zones.sh`, then compare junction-seam gaps, opening-segment lengths, and `validate()` warnings against the previous `zones.json`. The full switch produced 6 validation warnings and fails `test_data_sanity`.

**When the authority is wrong** (`validator._limit_is_plausible`): the KML lists the class-I Ихтиман–Мирово section of Път I-8 with the full motorway set (140/90/100) — most likely inherited from the adjacent Вакарел–Ихтиман entry, which really is on A-1. `MAX_LIMIT_KMH` demotes any per-field value impossible for the road class, whatever its source, so the merge falls through to 90/80/80. 140 km/h is not legal on any class-I road in Bulgaria and the error direction costs the driver a fine, so the override stands (decision confirmed 2026-08-08). It is **logged on every run** (`… KML limit is impossible for this road class and was overridden …`) rather than raised as a `validate()` warning — an upstream error we have consciously corrected is not a defect in the run, and a warning would fail `test_data_sanity` until BG TOLL fixes their map. If they fix it, the override stops firing on its own.

**Merge orientation reconciliation** (`validator._orient_to`, run inside `merge_match`): sources may list the same physical carriageway with opposite endpoint order, and the matcher accepts reversed pairs — so before per-endpoint fields are merged, every secondary source is reoriented to the primary (geometric endpoint comparison when both have coords; settlement-name orientation, then km-order vs `ROAD_DIRECTIONS`, for the coordinate-less BG TOLL). Without this, a reverse-matched pair crosses settlements/km markers onto the opposite carriageway's geometry — 21 shipped sections had swapped Latin/Cyrillic names and end-attached km markers before the fix. The matcher itself is junction-safe: `_km_ranges_overlap` requires ≥50% overlap of the shorter range (consecutive zones *touch* at a shared camera and must not match) and `_coords_close` requires both endpoints to coincide.

**Source failure = run failure** (`output.SourceFailure`): each active source scraper (`bgtoll`, `tolltracker`, `kml`) *raises* on fetch/parse failure (only per-item parse errors are skipped), and `run_pipeline` treats an exception **or an empty result** from any source as fatal — after attempting every source, it raises `SourceFailure` listing all of them, and `main()` exits 1 without writing (existing files untouched). Publishing with a source missing would silently degrade the data (the 2026-07 TollTracker redesign shipped a refresh that lost coordinates + Latin names on all 72 zones this way). `main()` re-logs the concise per-source errors *last*, so the Telegram failure message — which tails the final 30 lines of `cron.log` — always shows exactly what broke.

**Publish guard** (`output.publish_guard_errors`, enforced in `main()` for both `--output` and `--target-dir`): second net behind `SourceFailure`, against *partial* collapse that per-source failure detection can't see (a source quietly losing most of its zones) — refuses to write (exit 1, existing files untouched) when fewer than `MIN_PUBLISH_ZONES` (50) zones, any required motorway missing, (target-dir mode) the count dropping below 70% of the served `version.json` `zone_count`, **any single zone being unusable** (`output.unusable_zone_errors`: placeholder `(0, 0)` endpoints, a centerline under 2 points, a non-positive `distance_m`), or **any zone missing a car/truck/bus limit** (`output.incomplete_limit_errors`). Those last two are the 2026-08 Път I-8 net — see "New roads must be added to the direction tables" below. `tests/test_data_sanity.py` runs the same guard over the *committed* snapshot, so what refuses to publish also refuses to be committed.

**Never serve data a published client can't parse** (`src/client_contract.py` + `contracts/`). The publish guard's client rules are not hand-written `if`s — they live in `contracts/wire-v1.json`, a transcription of the decode surface of every app **actually in a store**, and `publish_guard_errors` refuses to write when the payload violates one. Read `contracts/README.md` before touching any of it. The three things that make it more than an assertion:

1. **Only published versions count.** `contracts/manifest.json` lists 1.0.4 and 1.1.0 — the only two releases that ever reached users. Tags v1.0.1–v1.0.3 exist in git but shipped to nobody, so they impose no obligation. Both entries share `wire-v1.json`: their decode surface is byte-identical (the diffs between those tags are `.use {}` resource-closing in `ZoneApi.kt`, an `avgSpeed` change on a non-wire type, and doc comments). Every published client is enforced at **ERROR** — a client-side fix can never reach an install that already exists, so "old enough to break" is not something a release date decides. Retire a version to WARN by adding an explicit `severity` to its manifest entry, deliberately: on the day 2.0.0 goes live, 1.1.0 is still the entire installed base.
2. **Every rule is proved against the real clients.** Each constraint has a fixture under `contracts/fixtures/` violating exactly that rule, and `contracts/verify_against_clients.sh` checks each published tag out into a git worktree, compiles a decoder from *that tag's* `Models.swift` + `ApiTypes.swift`, and asserts the outcome matches `fixtures/expectations.json`. Run it on macOS (never on the host — Python only there): `bash scrapers/contracts/verify_against_clients.sh`. Note `swift_decode: "tolerated"` is a pinned, legitimate outcome: an empty centerline decodes perfectly on iOS and destroys the Android *map*, so some rules exist for reasons the Swift decoder cannot see. Don't "fix" those to expect a failure that will never come.
3. **Drift fails the build.** `contracts/check_drift.py` fingerprints the field declarations of the four decode-surface files and `test_client_contract.py` recomputes it, so adding, removing, renaming or re-nullabling a field on `Zone`/`SpeedLimits`/`ZoneEndpoint`/`ZonesResponse` fails immediately; doc comments and helper methods don't move it. Those client paths are in `scraper.yml`'s PR trigger so the check actually runs when they change. After reviewing the contract against the new model, re-record with `python scrapers/contracts/check_drift.py --update`.

**The wire format is the only protection the published apps have.** `truck`/`bus` are optional at the *source* level but never on the wire, and a missing limit is a **publish blocker rather than a warning** because the clients in the stores are 1.x and 1.x has no tolerance for it: iOS 1.x decodes `SpeedLimits` with a synthesized `Codable`, so one absent key throws `keyNotFound` and fails the decode of the **entire** `/api/zones` response — zone sync dies for every published install, permanently, with no client-side recovery — while Android 1.x's Gson zero-fills and shows a truck/bus driver a 0 km/h limit. Current builds repair both (`ZoneSanitizer`, the `SpeedLimits` decoder), but **a fix that ships in an app cannot reach the installs already out there.** Until 2.x is what the stores serve, assume any zone this pipeline publishes must be consumable by a client with zero defensive parsing.

**New roads must be added to the direction tables** (`roads.ROAD_AXIS` + `ROAD_DIRECTIONS`). A road absent from both still gets a `direction` label, but from two *different* fallbacks: the bearing quadrant for the coordinate-bearing sources, "increasing km = east" for the coordinate-less BG TOLL. On a diagonal section those disagree — and since `match_zones` groups by `(road, direction)`, the same physical section then lands in two groups and publishes **twice**: once from BG TOLL with `(0, 0)` endpoints and an empty centerline, once from TollTracker with only a `car` limit. That shipped in 2026-08 when Път I-8 (Ихтиман – Мирово, diagonal NW–SE) appeared: 76 zones on the wire, of which 2 were unusable, which blanked the *entire* Android map (MapLibre rejects a whole FeatureCollection over one zero-point LineString) and threw `keyNotFound` out of the iOS decode. `validate()` now warns by name when a zone's road is missing from either table, and the publish guard refuses the unusable output outright. Both clients also drop such zones defensively (`ZoneSanitizer`, Kotlin + Swift twins) — a tourniquet, not a substitute for the tables.

**Road-class limit plausibility** (`validator._limit_is_plausible`, applied per field inside `_pick_limit`): KML outranks every other source for speed limits — correctly, it is the only one carrying the full per-category set — but it publishes the **motorway** set (140/90/100) for the class-I Път I-8 section, against the 90/80/80 that BG TOLL *and* TollTracker report. `MAX_LIMIT_KMH` holds per-vehicle ceilings by road class (`is_motorway`), and a source proposing an impossible value for the road class is skipped for that field so the next source wins. Checked per field because the ceilings differ by vehicle: truck 90 is legitimate on a motorway and wrong on a class-I road even when the car value alone wouldn't reveal it. If *every* source is implausible the top-ranked value is kept and `validate()` warns — better a loud wrong number than a missing one. The error direction is what makes this worth a guard: an over-permissive limit tells a driver 140 is fine at a 90 km/h camera.

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
| `~/srednabg_com/api/version.json` | Live, atomically replaced. Served as `/api/version`. `map_hash` **must stay `null`** — see below. |
| `~/srednabg_com/api/zones-<UTC-timestamp>.json` | Snapshot saved on every content change; newest 26 retained (~6 months at weekly cadence). |

`--target-dir` mode in `src/output.py` is the production entry point: it atomic-writes both files (`*.tmp` → `os.replace`) and snapshots the prior `zones.json` only when content changed. `--output` remains for one-shot local runs.

**`map_hash` must remain `null` on the production host until the map-bundle pipeline actually ships.** `src/output.py` hardcodes it to `None`, which is correct: the host serves no `/api/map/bundle.zip`, so a non-null hash would put the wire response ahead of what the host can serve. Both clients currently ignore the field (`FeatureFlags.IS_MAP_SYNC_ENABLED` / `.isMapSyncEnabled` are `false`, and `qa/scenarios/sync/map_disabled.py` pins the *Skipped* shape), so nothing breaks today — but the moment either flag flips, a populated `map_hash` would make the first sync round see a mismatch and chase a bundle endpoint that 404s. Note `backend/data/version.json` *does* carry a real `map_hash`: `backend/scripts/build-map-bundle.sh` patches it in for the locally-built bundle. That file is the local build artifact, not the deployed one — don't copy it to the host.

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
