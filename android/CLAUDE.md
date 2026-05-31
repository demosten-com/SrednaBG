# android/

Kotlin app using Jetpack Compose, Car App Library, MapLibre, Room, Hilt. ~40 Kotlin files in `main/` + 8 test files + 2 debug-only sources (`DebugSyncReceiver`, `DebugControlReceiver`). Phone app is the shipping surface: Home, ZoneMap, and Settings screens (TripHistory commented out pending implementation), running as a foreground location service that also doubles as a background audio service alongside Waze/Google Maps. Release signing is wired (`app/build.gradle.kts`): the `release` signing config activates whenever the four `SREDNABG_RELEASE_*` Gradle properties are present (set in `~/.gradle/gradle.properties` or `-P` flags), so the keystore stays outside the repo. The Car App Library / Android Auto target is WIP — kept in-tree for developer testing on DHU and AAOS, excluded from the Play Store release.

## Runtime

`LocationTrackingService` (foreground, adaptive 1s/5s GPS via the flavor-specific `LocationSource` — `FusedLocationProviderClient` on `gms`, platform `LocationManager` on `aosp`; see "Product flavors" below) feeds the core engine (`core/`). A second `lifecycleScope` coroutine runs the inactivity auto-stop: tracks `lastActivityMs` (monotonic, reset on tracking start and on every `ZoneState` class transition), polls `SettingsRepository.autoStopHours` every 60 s, and calls `stopSelf()` when the threshold elapses (the DEBUG-only `debug_auto_stop_seconds` override drops the check cadence to 1 s so the QA scenario fires in ~10 s instead of 3 h). Phone-side `ZoneMapScreen` uses MapLibre against a fully-offline bundled map; `ZoneMapViewModel.styleUri` = `MapRepository.localStyleUri()`, falling back to `BuildConfig.MAP_STYLE_URL` only when no bundle is installed. `AudioAlertManager` uses TTS with navigation audio focus for background mode. *(WIP / dev-only)* On the Android Auto surface, `NavigationScreen` renders a canvas-based zone map (`MapRenderer` + custom `MercatorProjection`) with `SpeedOverlay`; `NavigationTemplate.mapActionStrip` carries +/- zoom controls that flow into `MapRenderer.draw(zoomOverride)`.

`ZoneRepository.syncFromServer()` returns `SyncResult` (`Updated | UpToDate | Failed`) consumed by `ZoneSyncWorker` (WorkManager, 6h) and surfaced as Snackbars + retry CTA; falls back to bundled `zones.json`. `MapSyncWorker` (6h, unmetered-only) would pull `/api/map/bundle.zip` when `map_hash` from `/api/version` changes — **currently feature-gated off** (`FeatureFlags.IS_MAP_SYNC_ENABLED = false` in `app/src/main/kotlin/com/demosten/srednabg/app/FeatureFlags.kt`) because the production backend doesn't serve the bundle endpoint or populate `map_hash` yet. The gate is enforced both at `SrednaBGApp.onCreate` (don't enqueue the periodic work) and inside `MapSyncWorker.doWork` (early-return `Result.success()` to no-op any WorkManager queue persisted from a prior install). Mirrors `FeatureFlags.isMapSyncEnabled` on iOS; flip both when the backend pipeline ships. Room (`ZoneDatabase`/`ZoneDao`/`ZoneEntity`) for local persistence. Full Hilt DI.

## Permission gate

`PermissionRepository` (singleton, Hilt) is the single source of truth for `ACCESS_FINE_LOCATION`, `ACCESS_BACKGROUND_LOCATION`, `POST_NOTIFICATIONS`, and `isIgnoringBatteryOptimizations`. `rememberPermissionHandler` (called from `MainActivity`) drives the first-launch prompt sequence, auto-chaining fine → background only — `POST_NOTIFICATIONS` is intentionally NOT auto-chained because surfacing it without context confused users into denying it. `HomeScreen` observes the repository's `StateFlow` and calls `refresh()` on every `Lifecycle.Event.ON_RESUME` so changes the user makes in app-Settings show up immediately on return.

The HomeScreen state machine swaps the StartStop button for one of three advisory cards in priority order: **PermissionCard** (fine or background missing — only blocker; "Open Settings" is the recovery path), **NotificationCard** (T+ POST_NOTIFICATIONS missing — fires the system dialog inline, with Open Settings as the fallback for "Don't ask again"), **BatteryOptimizationCard** (whitelist nudge — fires `Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` directly via `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` permission, no Settings excursion). `HomeViewModel.startTracking()` re-checks `PermissionState.canStartTracking` server-side as a defense-in-depth gate. `MainActivity` toggles `FLAG_KEEP_SCREEN_ON` on the activity window while `LocationTrackingService.isTracking` is true (any tab); it's cleared on dispose to avoid leaking the flag.

UI has BG + EN (`res/values/strings.xml`, `res/values-bg/strings.xml`).

## Build commands

```bash
# Gradle Kotlin DSL, JDK 17 — run from android/ (this folder is the Gradle root)
./gradlew build                       # Full build (all flavors)
./gradlew :app:test                   # Unit tests, all variants (JUnit 5, MockK, Turbine)
./gradlew :app:testAospDebugUnitTest  # aosp-flavor unit tests only
./gradlew :app:testGmsDebugUnitTest   # gms-flavor unit tests only
./gradlew :app:assembleAospDebug      # aosp Debug APK (LocationManager; F-Droid + GitHub)
./gradlew :app:assembleGmsDebug       # gms Debug APK (FusedLocationProvider; Play Store)
./gradlew :app:assembleAospRelease    # aosp Release APK (R8 minified) — GitHub Releases
./gradlew :app:assembleGmsRelease     # gms Release APK (R8 minified) — Play Store
./gradlew lint                        # Lint
```

### Product flavors (`distribution` dimension)

The app ships in two flavors that differ **only in the GPS location provider**;
all other code is shared in `src/main/`.

| Flavor | Location source | Google Play Services | Ships to |
|--------|-----------------|----------------------|----------|
| `aosp` (default) | `SystemLocationSource` (platform `LocationManager`) | none | F-Droid + GitHub Releases |
| `gms` | `FusedLocationProviderClient`, falling back to `LocationManager` on AAOS or when Play Services is unavailable | `play-services-location` (`gmsImplementation`) | Play Store |

The provider-specific `createLocationSource(context, listener)` factory lives in
`src/aosp/` and `src/gms/` (the gms one also holds `FusedLocationSource` and the
pure `chooseLocationSourceKind()` fallback policy + its unit test). `src/main/`
references no GMS type, so the aosp variant compiles without
`play-services-location` and passes F-Droid's flavor-aware source scanner. Both
flavors log the chosen source under `SrednaBG.LocSrc` (`Selecting
{Fused,System}LocationSource`); the QA harness asserts this matches the
installed flavor (see `qa/CLAUDE.md`, `--flavor`).

Pushing a tag matching `v[0-9]+.[0-9]+.[0-9]+` triggers `.github/workflows/android-release.yml`, which builds a signed APK (`-PSREDNABG_VERSION_NAME` / `-PSREDNABG_VERSION_CODE` overrides parsed from the tag; `MAJOR*10000 + MINOR*100 + PATCH`) and attaches `srednabg-<version>.apk` + `.sha256` to a GitHub Release.

Release builds set `ndk { debugSymbolLevel = "SYMBOL_TABLE" }` so the AAB bundles a symbol table for MapLibre's `libmapbox-gl.so` — Play Console can then symbolicate native crashes/ANRs without the "missing debug symbols" upload warning. `SYMBOL_TABLE` keeps the size hit small (function names only); `FULL` would also embed line numbers but balloons the AAB.

Map bundle fetch: the workflow downloads `https://srednabg.com/assets/map-bundle-<tag>.zip` and verifies it against the SHA-256 listed for that tag in `web/fdroid/map-bundle-checksums.txt`. Before tagging, run `bash web/fdroid/scripts/publish-map-bundle.sh <tag>` locally to rebuild + hash the bundle and commit the updated checksums file (the script also prints the SCP command for manual upload to Namecheap). The optional `MAP_BUNDLE_URL` repo secret overrides the URL and skips the hash check — useful for hotfix tags where re-uploading the bundle is impractical.

Required repo secrets: `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`. Optional: `MAP_BUNDLE_URL` (override).

## Offline map bundle (Android side)

Bundle is produced by `backend/scripts/build-map-bundle.sh` — see `backend/CLAUDE.md` for the build pipeline.

1. **Stage** (`validateMapBundle` + `prepareMapAssets` Gradle tasks, wired to `preBuild`): copies `backend/data/map-bundle/` into `android/app/src/main/assets/map/`. `validateMapBundle` FAILS the build if the source dir is missing or doesn't contain `style-light.json`, `style-dark.json`, and `bulgaria.mbtiles` (the `requiredMapFiles` list) — offline-first means shipping without the bundle would hand users a blank map. `assets/map/` is gitignored.
2. **Install** (`MapRepository.ensureLoaded()`): on first launch, copies `assets/map/` into `filesDir/map/` (SQLite can't mmap APK assets) and rewrites placeholders to absolute `mbtiles://` / `file://` paths. The MBTiles URI must be bare `mbtiles://<abs-path>` — **no `{z}/{x}/{y}`** — or MapLibre's `MBTilesFileSource` fails to open SQLite.
3. **Sync** (`MapSyncWorker` → `MapRepository.syncFromServer()`): compares server `map_hash` to `SettingsRepository.cachedMapHash`, downloads zip via `MapApi`, unzips into `map.staging/`, validates `style-light.json` + `style-dark.json` + `bulgaria.mbtiles` present, atomically renames `map/ → map.old/`, `map.staging/ → map/`, deletes `map.old/`. Any failure leaves the previous bundle intact.

## Debug receivers (debug build only)

`DebugSyncReceiver` forces a sync from adb (watch `adb logcat -s DebugSync`):

```bash
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugSyncReceiver -a com.demosten.srednabg.debug.SYNC_MAP
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugSyncReceiver -a com.demosten.srednabg.debug.SYNC_ZONES
```

`SYNC_MAP` logs `... -> Skipped (feature disabled)` while `FeatureFlags.IS_MAP_SYNC_ENABLED` is `false` and does not reach `MapRepository.syncFromServer`. `qa/scenarios/sync/map_disabled.py` asserts this shape — re-enabling the flag without restoring the happy-path scenario will fail the QA sync suite.

`DebugControlReceiver` is the QA harness's control surface — flips any user-settable preference through the same `SettingsRepository` typed setters the UI uses, and starts/stops `LocationTrackingService` (the foreground service is `exported="false"`, so a plain `am start-foreground-service` is blocked). All applied changes log under tag `DebugSettings`.

```bash
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
    -a com.demosten.srednabg.debug.SET_SETTING --es key vehicle_type --es value truck
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
    -a com.demosten.srednabg.debug.START_TRACKING
adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
    -a com.demosten.srednabg.debug.STOP_TRACKING
```

Settable keys: `vehicle_type`, `app_language`, `voice_enabled`, `periodic_voice_updates`, `announce_only_when_over`, `alert_threshold_kmh`, `map_heading_up`, `auto_stop_hours`, `cached_zone_hash`, `cached_map_hash`, and the DEBUG-only `debug_auto_stop_seconds` / `debug_max_speed_override` overrides used by the QA harness.

## Drive simulation (AAOS emulator)

Exercises the full GPS pipeline without a real car. For manual exploration; for repeatable assertions prefer the QA harness (see `qa/CLAUDE.md`).

1. Generate GPX: `cd scrapers && python scripts/make_test_route.py --out /tmp/route.gpx`.
2. AAOS emulator → Extended Controls (`⋯`) → Location → Routes → Import GPX → Play 1x. `LocationTrackingService` picks it up via FLP; `NavigationScreen` renders polyline + speed overlay; phone Home walks `outside → in-zone → exiting`.
3. If FLP ignores mocks: Developer Options → *Select mock location app* → SrednaBG (rarely needed on emulator).

## Key files

- Android Auto (WIP, dev-only target): `NavigationScreen.kt`, `SpeedOverlay.kt`, `MapRenderer.kt`, `MercatorProjection.kt`, `SrednaBGSession.kt`
- Services: `LocationTrackingService.kt`, `AudioAlertManager.kt`
- Data: `ZoneRepository.kt` (+`SyncResult`), `ZoneDatabase.kt`, `ZoneSyncWorker.kt`, `MapRepository.kt`, `MapSyncWorker.kt`; remote: `ZoneApi.kt` (`map_hash` in `VersionResponse`), `MapApi.kt` (`/api/map/bundle.zip`)
- Permissions: `permissions/PermissionRepository.kt` (+`PermissionState`), `ui/components/PermissionHandler.kt` (first-launch prompt chain)
- Phone UI: `HomeScreen.kt` (+ `PermissionCard` / `NotificationCard` / `BatteryOptimizationCard`), `ZoneMapScreen.kt`, `SettingsScreen.kt`; DI: `AppModule.kt`, `SrednaBGApp.kt` (schedules both sync workers)
- Tests: `app/src/test/kotlin/.../HomeViewModelTest.kt` covers the permission gate (notification + battery-opt are advisory, not blockers)
- Debug (`src/debug/`): `DebugSyncReceiver.kt`, `DebugControlReceiver.kt` + manifest overlay
- Config: `res/drawable/ic_add.xml` / `ic_remove.xml` (AA zoom icons). No `network_security_config.xml` — both debug and release use HTTPS, so the platform default (cleartext denied) applies.
- Build: `app/build.gradle.kts` `prepareMapAssets` Copy task stages `backend/data/map-bundle/` → `assets/map/` before `preBuild`

## Dependencies (`gradle/libs.versions.toml`)

Kotlin 2.1.10, AGP 8.8.2, Compose BOM 2025.02.00, Car App Library 1.7.0, MapLibre 11.8.0, Room 2.7.1, Hilt 2.56.2, OkHttp 4.12.0, Coroutines 1.10.1, Play Services Location 21.3.0 (`gmsImplementation` — gms flavor only), MockK 1.13.14, Turbine 1.2.1.

## Remaining work

- **Backend URLs**: `ZONE_API_BASE_URL` and `MAP_STYLE_URL` are set in `defaultConfig` at `https://srednabg.com` for both debug and release — every build talks to the Namecheap-hosted `/api/zones` + `/api/version`. `MAP_STYLE_URL` (`https://srednabg.com/tiles/styles/basic-preview/style.json`) is a fallback only; runs use the on-disk bundle via `MapRepository.localStyleUri()`. The `/tiles/...` path doesn't exist on the production host yet — the fallback only fires if the in-APK bundle is broken.
- **Play Store listing**: store description, content rating, final upload. Play subtitle: Секционен контрол — средна скорост. Keywords: средна скорост, секционен контрол, камери, отсечки, БГ ТОЛ, скорост, автомагистрала. Play Store targets BG only. Screenshots are produced by the `/screenshot-app` + `/frame-screenshots` skills (raw PNGs from the emulator, then Waze-style framed PNGs from those — see `qa/CLAUDE.md` "Store-screenshot tooling" for the workflow).
- **TripHistoryScreen**: commented out from navigation; implement when ready
- **Battery optimization**: GPS/wake-lock refinement; geofencing API for zone proximity
- **Instrumented tests**: no `androidTest/` yet (JVM units cover ViewModels/repos/mappers). The absence hid a latent manifest bug (`android:name=".SrednaBGApp"` vs `com.demosten.srednabg.app.*` packages) until first on-device run
- **Upgrade path**: Android Studio re-prompts AGP 9 / Gradle 9 / Kotlin 2.2 / compileSdk 37 — decline until Hilt/KSP/Compose BOM matrix supports it
