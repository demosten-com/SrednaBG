# android/

Kotlin app using Jetpack Compose, Car App Library, MapLibre, Room, Hilt. ~36 Kotlin files in `main/` + 7 test files + 2 debug-only sources (`DebugSyncReceiver`, `DebugControlReceiver`). Phone app is the shipping surface: Home, ZoneMap, and Settings screens (TripHistory commented out pending implementation), running as a foreground location service that also doubles as a background audio service alongside Waze/Google Maps. The Car App Library / Android Auto target is WIP — kept in-tree for developer testing on DHU and AAOS, excluded from the Play Store release (see `test-data/android-release.md`).

## Runtime

`LocationTrackingService` (foreground, adaptive 1s/5s GPS via `FusedLocationProviderClient`) feeds the core engine (`core/`). Phone-side `ZoneMapScreen` uses MapLibre against a fully-offline bundled map; `ZoneMapViewModel.styleUri` = `MapRepository.localStyleUri()`, falling back to `BuildConfig.MAP_STYLE_URL` only when no bundle is installed. `AudioAlertManager` uses TTS with navigation audio focus for background mode. *(WIP / dev-only)* On the Android Auto surface, `NavigationScreen` renders a canvas-based zone map (`MapRenderer` + custom `MercatorProjection`) with `SpeedOverlay`; `NavigationTemplate.mapActionStrip` carries +/- zoom controls that flow into `MapRenderer.draw(zoomOverride)`.

`ZoneRepository.syncFromServer()` returns `SyncResult` (`Updated | UpToDate | Failed`) consumed by `ZoneSyncWorker` (WorkManager, 6h) and surfaced as Snackbars + retry CTA; falls back to bundled `zones.json`. Parallel `MapSyncWorker` (6h, unmetered-only) pulls `/api/map/bundle.zip` when `map_hash` from `/api/version` changes. Room (`ZoneDatabase`/`ZoneDao`/`ZoneEntity`) for local persistence. Full Hilt DI.

UI has BG + EN (`res/values/strings.xml`, `res/values-bg/strings.xml`).

## Build commands

```bash
# Gradle Kotlin DSL, JDK 17 — run from android/ (this folder is the Gradle root)
./gradlew build                  # Full build
./gradlew :app:test              # Unit tests (JUnit 5, MockK, Turbine)
./gradlew :app:assembleDebug     # Debug APK
./gradlew :app:assembleRelease   # Release APK (R8 minified)
./gradlew lint                   # Lint
```

## Offline map bundle (Android side)

Bundle is produced by `backend/scripts/build-map-bundle.sh` — see `backend/CLAUDE.md` for the build pipeline.

1. **Stage** (`validateMapBundle` + `prepareMapAssets` Gradle tasks, wired to `preBuild`): copies `backend/data/map-bundle/` into `android/app/src/main/assets/map/`. `validateMapBundle` FAILS the build if the source dir is missing or doesn't contain both `style.json` and `bulgaria.mbtiles` — offline-first means shipping without the bundle would hand users a blank map. `assets/map/` is gitignored.
2. **Install** (`MapRepository.ensureLoaded()`): on first launch, copies `assets/map/` into `filesDir/map/` (SQLite can't mmap APK assets) and rewrites placeholders to absolute `mbtiles://` / `file://` paths. The MBTiles URI must be bare `mbtiles://<abs-path>` — **no `{z}/{x}/{y}`** — or MapLibre's `MBTilesFileSource` fails to open SQLite.
3. **Sync** (`MapSyncWorker` → `MapRepository.syncFromServer()`): compares server `map_hash` to `SettingsRepository.cachedMapHash`, downloads zip via `MapApi`, unzips into `map.staging/`, validates `style.json` + `bulgaria.mbtiles` present, atomically renames `map/ → map.old/`, `map.staging/ → map/`, deletes `map.old/`. Any failure leaves the previous bundle intact.

## Debug receivers (debug build only)

`DebugSyncReceiver` forces a sync from adb (watch `adb logcat -s DebugSync`):

```bash
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugSyncReceiver -a com.demosten.srednabg.debug.SYNC_MAP
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugSyncReceiver -a com.demosten.srednabg.debug.SYNC_ZONES
```

`DebugControlReceiver` is the QA harness's control surface — flips any user-settable preference through the same `SettingsRepository` typed setters the UI uses, and starts/stops `LocationTrackingService` (the foreground service is `exported="false"`, so a plain `am start-foreground-service` is blocked). All applied changes log under tag `DebugSettings`.

```bash
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
    -a com.demosten.srednabg.debug.SET_SETTING --es key vehicle_type --es value truck
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
    -a com.demosten.srednabg.debug.START_TRACKING
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
    -a com.demosten.srednabg.debug.STOP_TRACKING
```

Settable keys: `vehicle_type`, `app_language`, `voice_enabled`, `periodic_voice_updates`, `announce_only_when_over`, `alert_threshold_kmh`, `map_heading_up`, `cached_zone_hash`, `cached_map_hash`.

## Drive simulation (AAOS emulator)

Exercises the full GPS pipeline without a real car. For manual exploration; for repeatable assertions prefer the QA harness (see `qa/CLAUDE.md`).

1. Generate GPX: `cd scrapers && python scripts/make_test_route.py --out /tmp/route.gpx`.
2. AAOS emulator → Extended Controls (`⋯`) → Location → Routes → Import GPX → Play 1x. `LocationTrackingService` picks it up via FLP; `NavigationScreen` renders polyline + speed overlay; phone Home walks `outside → in-zone → exiting`.
3. If FLP ignores mocks: Developer Options → *Select mock location app* → SrednaBG (rarely needed on emulator).

## Key files

- Android Auto (WIP, dev-only target): `NavigationScreen.kt`, `SpeedOverlay.kt`, `MapRenderer.kt`, `MercatorProjection.kt`, `SrednaBGSession.kt`
- Services: `LocationTrackingService.kt`, `AudioAlertManager.kt`
- Data: `ZoneRepository.kt` (+`SyncResult`), `ZoneDatabase.kt`, `ZoneSyncWorker.kt`, `MapRepository.kt`, `MapSyncWorker.kt`; remote: `ZoneApi.kt` (`map_hash` in `VersionResponse`), `MapApi.kt` (`/api/map/bundle.zip`)
- Phone UI: `HomeScreen.kt`, `ZoneMapScreen.kt`, `SettingsScreen.kt`; DI: `AppModule.kt`, `SrednaBGApp.kt` (schedules both sync workers)
- Debug (`src/debug/`): `DebugSyncReceiver.kt`, `DebugControlReceiver.kt` + manifest overlay
- Config: `res/drawable/ic_add.xml` / `ic_remove.xml` (AA zoom icons). No `network_security_config.xml` — both debug and release use HTTPS, so the platform default (cleartext denied) applies.
- Build: `app/build.gradle.kts` `prepareMapAssets` Copy task stages `backend/data/map-bundle/` → `assets/map/` before `preBuild`

## Dependencies (`gradle/libs.versions.toml`)

Kotlin 2.1.10, AGP 8.8.2, Compose BOM 2025.02.00, Car App Library 1.7.0, MapLibre 11.8.0, Room 2.7.1, Hilt 2.56.2, OkHttp 4.12.0, Coroutines 1.10.1, Play Services Location 21.3.0, MockK 1.13.14, Turbine 1.2.1.

## Remaining work

- **Release signing**: keystore + `signingConfigs` in build.gradle.kts
- **Backend URLs**: `ZONE_API_BASE_URL` and `MAP_STYLE_URL` are set in `defaultConfig` at `https://srednabg.com` for both debug and release — every build talks to the Namecheap-hosted `/api/zones` + `/api/version`. `MAP_STYLE_URL` (`https://srednabg.com/tiles/styles/basic-preview/style.json`) is a fallback only; runs use the on-disk bundle via `MapRepository.localStyleUri()`. The `/tiles/...` path doesn't exist on the production host yet — the fallback only fires if the in-APK bundle is broken.
- **Play Store listing**: screenshots, store description, content rating. Play subtitle: Секционен контрол — средна скорост. Keywords: средна скорост, секционен контрол, камери, отсечки, БГ ТОЛ, скорост, автомагистрала. Play Store targets BG only.
- **TripHistoryScreen**: commented out from navigation; implement when ready
- **Battery optimization**: GPS/wake-lock refinement; geofencing API for zone proximity
- **Instrumented tests**: no `androidTest/` yet (JVM units cover ViewModels/repos/mappers). The absence hid a latent manifest bug (`android:name=".SrednaBGApp"` vs `com.demosten.srednabg.app.*` packages) until first on-device run
- **Upgrade path**: Android Studio re-prompts AGP 9 / Gradle 9 / Kotlin 2.2 / compileSdk 37 — decline until Hilt/KSP/Compose BOM matrix supports it
