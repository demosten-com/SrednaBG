## Project Overview

SrednaBG (Средна БГ) is a free, open-source Android + iOS phone app that tracks real-time running average speed within Bulgaria's section control (секционен контрол) camera zones. It fills the gap where Waze shows zone alerts but doesn't calculate average speed or the max speed sustainable for the remainder of the zone. Android Auto and CarPlay surfaces exist in the codebase as WIP and are not part of the initial release.

Package ID: `com.demosten.srednabg` | Bulgaria-only scope | MIT license.

## Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Monorepo scaffolding, Gradle, CI/CD | Done |
| 2 | Zone data schema and Python scrapers | Done (`zones.json` populated with 100+ real zones) |
| 3 | Core calculation engine (pure Kotlin) | Done + comprehensive tests |
| 4 | Backend infrastructure (Docker, nginx) | Done (Planetiler-generated Bulgaria tiles, tileserver-gl verified) |
| 5 | Android app foundation (phone UI) | Done (Compose UI, Room, Hilt, location service, audio alerts) |
| 6 | Android Auto integration | Done in code — WIP, not in initial release (kept for developer testing on DHU/AAOS) |
| 7 | Polish, testing, release prep | Mostly done — signing + Play listing remain (see `android/CLAUDE.md`) |
| 8a | iOS phone port (Swift 6 + SwiftUI) | Functionally complete. App Store submission is Phase 8c. |
| 8b | CarPlay | WIP — not in initial release. Code complete (`SrednaBGCarPlay` package — scene delegate, `CPMapTemplate`, `CPNavigationSession`). **Unwired from the app target** until Apple grants `com.apple.developer.carplay-navigation` (iOS 18+ Simulator's `amfi` rejects the un-granted entitlement). Re-link path is documented in `ios/CLAUDE.md`. |
| 8c | Phone-only App Store release | Privacy manifest, App Store metadata + screenshots, TestFlight, App Store submission. CarPlay entitlement filed once TestFlight build exists. |

## Monorepo Layout

Each subfolder owns its own `CLAUDE.md` with build commands, key files, and subfolder-specific notes. Start there when working in that area.

- `scrapers/` — Python data pipeline (3 sources → `zones.json`). See `scrapers/CLAUDE.md`.
- `android/` — Kotlin phone app (Compose UI, offline map, WorkManager sync); the Android Auto target is in-tree as WIP (developer-only testing on DHU/AAOS, not part of the shipping build). Pure-Kotlin engine at `android/core/` (see `android/core/CLAUDE.md`); the rest is in `android/CLAUDE.md`.
- `backend/` — Docker stack (tileserver-gl + nginx) + offline map bundle builder. See `backend/CLAUDE.md`.
- `qa/` — End-to-end QA harness driving the emulator via adb. See `qa/CLAUDE.md`.
- `ios/` — SwiftPM monorepo (Swift 6) + Xcode app shell. See `ios/CLAUDE.md`.
- `web/` — Static marketing site for `srednabg.com`; same Namecheap host runs the scraper cron and serves `/api/*`. See `web/CLAUDE.md`.

## Three-Tier Data Flow

1. **Data ingestion** (Python → `scrapers/`) — scrapes BG TOLL HTML, TollTracker GeoJSON, OSM Overpass; merges into `zones.json` with version hash.
2. **Core engine** (Kotlin JVM → `android/core/`) — stateful zone detection, running-average + remainder-sustainable speed, Kalman-like GPS filtering. The iOS side has an independent Swift hand-port at `ios/Packages/SrednaBGCore/`.
3. **Apps** — `android/` (LocationTrackingService → MapLibre on AA Surface + phone Compose UI) and `ios/` (CLLocationManager → SwiftUI + MapLibre Native).

## Key Design Decisions

- **MapLibre over Google Maps/Mapbox** — zero per-request cost with self-hosted tiles
- **NavigationTemplate** — only AA template providing a Surface for custom map rendering
- **Pure Kotlin core** — testable without Android emulator; portable to iOS
- **Offline-first** — zones.json + map bundle ship in APK / iOS bundle; network sync is optional updates
- **Self-hosted Mac Mini** — no recurring cloud costs; 1 Gbit upload handles thousands of users
- **Adaptive GPS polling** — 1s inside zones, 5s when far from any zone (battery)
- **Map bundle in APK, not PAD** — mbtiles capped at z12 to fit the APK; avoids Play Asset Delivery so F-Droid / sideload stay open

## CI/CD

- `.github/workflows/android-build.yml` — on push/PR: core tests, assemble debug APK, lint, upload APK artifact
- `.github/workflows/scraper.yml` — PR validation only (scrapers/** path filter) + manual trigger; production scheduling lives on the Namecheap cron (see `scrapers/CLAUDE.md` "Hosted deployment")

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
- Motorcycle speed limits — separate limits needed?
- Custom user-reported zones — support for zones not yet officially certified?
- Cloudflare CDN for tiles — consider if user base grows
