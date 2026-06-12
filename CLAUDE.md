## Project Overview

SrednaBG (Средна БГ) is a free, open-source Android + iOS phone app that tracks real-time running average speed within Bulgaria's section control (секционен контрол) camera zones. It fills the gap where Waze shows zone alerts but doesn't calculate average speed or the max speed sustainable for the remainder of the zone. On Android, an opt-in floating overlay surfaces the live status over Waze/Google Maps; both platforms support per-vehicle-type speed limits (car/truck/bus/motorcycle). Android Auto and CarPlay surfaces exist in the codebase as WIP and are not part of the initial release.

Package ID: `com.demosten.srednabg` | Bulgaria-only scope | MIT license.

## Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Monorepo scaffolding, Gradle, CI/CD | Done |
| 2 | Zone data schema and Python scrapers | Done (`zones.json` ships ~72 real zones; exact count tracked by the scraper). The single source of truth is `backend/data/zones.json` — both apps bundle that same file (Android generates its asset at build time; see "Three-Tier Data Flow") |
| 3 | Core calculation engine (pure Kotlin) | Done + comprehensive tests. Self-orienting centerlines, polyline-projection remaining/exit, off-road exit hysteresis, vehicle-type-aware limits |
| 4 | Offline map-bundle build pipeline | Done (self-contained Planetiler-JAR builder; the former Docker/tileserver-gl serving stack is retired) |
| 5 | Android app foundation (phone UI) | Done (Compose UI, Room, Hilt, location service, audio alerts, opt-in draw-over-other-apps overlay, vehicle-type setting) |
| 6 | Android Auto integration | Done in code — WIP, not in initial release (kept for developer testing on DHU/AAOS) |
| 7 | Polish, testing, release prep | Signing wired; signed-APK release workflow shipping `srednabg-<version>.apk` + `.sha256` to GitHub Releases; F-Droid: build recipe **merged into `fdroiddata`** — the app publishes once F-Droid's build server signs the first build; `web/fdroid/` remains the source of truth for ongoing per-tag updates (metadata, locale descriptions, SHA-pinned map-bundle pipeline). Play Store: listing + screenshots done; v1.0.2 **approved and live in open testing**, promotable to production at the user's discretion (not yet promoted). See `android/CLAUDE.md` |
| 8a | iOS phone port (Swift 6 + SwiftUI) | Functionally complete (Xcode app shell, MapLibre map, Live Activity + Dynamic Island, permission gating). App Store submission is Phase 8c. |
| 8b | CarPlay | WIP — not in initial release. Code complete (`SrednaBGCarPlay` package — scene delegate, `CPMapTemplate`, `CPNavigationSession`). **Unwired from the app target** until Apple grants `com.apple.developer.carplay-navigation` (iOS 18+ Simulator's `amfi` rejects the un-granted entitlement). Re-link path is documented in `ios/CLAUDE.md`. |
| 8c | Phone-only App Store release | Privacy manifest, App Store metadata + screenshots all done; phone build **submitted — in App Store review as v1.0.2**. v1.0.4 held back from App Store Connect until v1.0.2 clears review (re-submitting would pull the in-review build). CarPlay entitlement filed once TestFlight build exists. |

## Monorepo Layout

Each subfolder owns its own `CLAUDE.md` with build commands, key files, and subfolder-specific notes. Start there when working in that area.

- `scrapers/` — Python data pipeline (3 sources → `zones.json`). See `scrapers/CLAUDE.md`.
- `android/` — Kotlin phone app (Compose UI, offline map, WorkManager sync); the Android Auto target is in-tree as WIP (developer-only testing on DHU/AAOS, not part of the shipping build). Pure-Kotlin engine at `android/core/` (see `android/core/CLAUDE.md`); the rest is in `android/CLAUDE.md`.
- `backend/` — Offline map-bundle builder (self-contained Planetiler JAR; no Docker) + local zone-data staging. See `backend/CLAUDE.md`.
- `qa/` — End-to-end QA harness driving the emulator via adb. See `qa/CLAUDE.md`.
- `ios/` — SwiftPM monorepo (Swift 6) + Xcode app shell. See `ios/CLAUDE.md`.
- `web/` — Static marketing site for `srednabg.com` (download cards link App Store, Play Store, and F-Droid); same Namecheap host runs the scraper cron and serves `/api/*`. Houses the F-Droid metadata source of truth in `web/fdroid/` (recipe now merged into `fdroiddata`); the latest map bundle lives on the rolling `map-bundle-latest` GitHub Release, not on the web host. See `web/CLAUDE.md`.

## Three-Tier Data Flow

1. **Data ingestion** (Python → `scrapers/`) — scrapes BG TOLL HTML, TollTracker GeoJSON, OSM Overpass; merges into `backend/data/zones.json` (the single source of truth, with a version hash) via `scrapers/scripts/refresh-zones.sh`. Both apps bundle that one file: iOS via a `Bundled Zones` Run Script phase, Android via the Gradle `prepareZonesAsset` task (copies it into `android/app/src/main/assets/zones.json` at build time — that asset is generated, gitignored, NOT committed, so the two platforms can't ship different zone data). The Gradle `checkZoneDataFreshness` task WARNS (never fails) when the source is older than 10 days.
2. **Core engine** (Kotlin JVM → `android/core/`) — stateful zone detection, running-average + remainder-sustainable speed, Kalman-like GPS filtering. The iOS side has an independent Swift hand-port at `ios/Packages/SrednaBGCore/`.
3. **Apps** — `android/` (LocationTrackingService → MapLibre on AA Surface + phone Compose UI) and `ios/` (CLLocationManager → SwiftUI + MapLibre Native).

## Key Design Decisions

- **MapLibre over Google Maps/Mapbox** — zero per-request cost with self-generated, in-app bundled tiles
- **NavigationTemplate** — only AA template providing a Surface for custom map rendering
- **Pure Kotlin core** — testable without Android emulator; portable to iOS
- **Offline-first** — zones.json + map bundle ship in APK / iOS bundle; network sync is optional updates
- **No recurring cloud costs** — offline-first apps need no tile server; the zone API runs on the existing Namecheap shared host (scraper cron), and map bundles are built locally / on a future Mac Mini CI runner
- **Adaptive GPS polling** — 1s inside zones, 5s when far from any zone (battery)
- **Inactivity auto-stop** — tracking shuts itself down after a settable timeout (default 3h, also 6h / Never) of no zone state transitions, so a forgotten-in-background session doesn't drain the battery. Setting key `auto_stop_hours`; QA scenarios dial it down via the DEBUG-only `debug_auto_stop_seconds` override
- **Map bundle in APK, not PAD** — mbtiles capped at z12 to fit the APK; avoids Play Asset Delivery so F-Droid / sideload stay open
- **Draw-over-other-apps overlay (Android)** — opt-in (default off), floats a compact badge between zones and the full live-average status in-zone over Waze/Maps via a `TYPE_APPLICATION_OVERLAY` window. Pure AOSP (no GMS, F-Droid-safe); needs the `SYSTEM_ALERT_WINDOW` special permission, routed from the Settings toggle. See `android/CLAUDE.md`
- **Vehicle types** — a `VehicleType` enum (car/truck/bus/motorcycle) in the core picks the per-vehicle speed limit per zone (motorcycle falls back to the car limit where a zone has none); exposed as a Settings choice with Kotlin + Swift parity. See `android/core/CLAUDE.md`
- **Single zone-data source of truth** — `backend/data/zones.json` is the one file both apps bundle; Android generates its asset from it at build time (see "Three-Tier Data Flow")

## CI/CD

- `.github/workflows/android-build.yml` — on push/PR: core tests, assemble debug APK, lint, upload APK artifact
- `.github/workflows/android-release.yml` — on `v*.*.*` tag: signed release APK + `.sha256` published to a GitHub Release. Downloads the latest map bundle from the rolling `map-bundle-latest` GitHub Release, verifies it against the single digest in `web/fdroid/map-bundle-checksums.txt`, and snapshots it onto the Release as an immutable `map-bundle-<tag>.zip` (+`.sha256`) — the durable build input F-Droid's prebuild fetches. The `MAP_BUNDLE_URL` secret is an optional override that skips the pin. See `android/CLAUDE.md` for the release tag → versionCode mapping.
- `.github/workflows/scraper.yml` — PR validation only (scrapers/** path filter) + manual trigger; production scheduling lives on the Namecheap cron (see `scrapers/CLAUDE.md` "Hosted deployment")

Per-locale F-Droid release notes go in `web/fdroid/{en-US,bg}/changelogs/<versionCode>.txt`.

Store assets (Play Store + App Store screenshots) are produced locally by the `/screenshot-app` skill (raw PNGs from the running emulator / Simulator) followed by `/frame-screenshots` (offline Waze-style framing). See `qa/CLAUDE.md` "Store-screenshot tooling".

## Development Workflow

Use Sonnet 4 as default; escalate to Opus 4 for architecture decisions or when stuck.

### Git policy

**Never use git for write operations** (no `add`, `commit`, `push`, `merge`, `rebase`, `reset`, `checkout -- <file>`, `branch -d`, `tag`, etc.). Read-only (`status`, `log`, `diff`, `show`, `blame`, `branch -l`) and local restore (`git restore`, `git checkout <file>`) are fine. The user handles all commits and pushes.

## Branding & Locale

- **App name:** SrednaBG (Средна БГ) | **Repo:** `demosten-com/SrednaBG` (https://github.com/demosten-com/SrednaBG)
- Zone data and BG TOLL scraping are Bulgarian Cyrillic; UI has BG + EN; Play Store targets BG only.
- Play Store listing details (subtitle, keywords) live in `android/CLAUDE.md`.

## Open Questions

- BG TOLL tolerance rumored at +3 km/h (≤100) / +3% (>100) — factor into the over-limit check if confirmed
- Per-vehicle limits are now modeled (car/truck/bus/motorcycle); motorcycle falls back to the car limit where a zone has no explicit value — confirm whether any zones actually differ for motorcycles
- Custom user-reported zones — support for zones not yet officially certified?
- Cloudflare CDN for tiles — consider if user base grows
