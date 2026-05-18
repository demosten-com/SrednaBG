# ios/

SwiftPM monorepo (Swift 6, strict concurrency) + Xcode app shell. **Initial release is phone-only.** Phase 8a complete (phone build). Phase 8b CarPlay is WIP — code complete but **unwired from the SrednaBG app target** pending Apple's `com.apple.developer.carplay-navigation` grant (iOS 18+ Simulator's `amfi` rejects the spawn when the un-granted entitlement is embedded — there's no developer-side workaround). Swift Testing suite green via `swift test` — covers all SPM packages including `SrednaBGCarPlay` overlay model + module registry and the `ZoneTrackingService` permission gate; iOS Simulator build green via `xcodebuild` for both Debug and Release with clean Automatic signing. Phase 8c — App Store submission of the phone-only build first; CarPlay re-wires if/when Apple grants.

## Packages

- **SrednaBGCore** — hand-port of Kotlin `android/core/`, zero deps. `ZoneDetector.update(_:vehicleType:)` honors the user's vehicle-type setting; the Kotlin core hardcodes `.car` — see `android/core/CLAUDE.md` for the backport note.
- **SrednaBGData** — URLSession actor (`SyncClient`), `SettingsStore`, `OfflineMapInstaller`, `BundledZonesLoader`, `ZoneStore`. Consumes `convertFromSnakeCase` JSON. Tests use `MockURLProtocol` (suite must be `.serialized` — the protocol's handler is process-wide static).
- **SrednaBGTracking** — CLLocationManager + AVSpeechSynthesizer + BackgroundTasks + ActivityKit. Pure-logic types (`AnnouncementPolicy`, `AdaptiveLocationCadence`, `BearingFallback`, `SpeedInference`, `TtsPhrases`) are macOS-testable; iOS-only files (`CLLocationTracker`, `BackgroundSyncScheduler`, `LiveActivityManager`) gated by `#if os(iOS)` (NOT `canImport(...)` — `BackgroundTasks` and `ActivityKit` import on macOS but their core symbols are unavailable). `ZoneTrackingService` is `@Observable @MainActor`, owns `ZoneDetector` (struct), publishes `zoneState` / `currentPosition` / `isTracking` / `permission` (`LocationPermission` — `unknown | always | whenInUse | denied`) to SwiftUI. `start()` runs the **two-step authorization flow** Apple requires for Always: prompt from `.notDetermined` → When-In-Use, then prompt again from `.authorizedWhenInUse` → Always. The gate **refuses to start tracking unless `.always` is granted** (When-In-Use silently dies on screen lock); the HomeScreen surfaces the resolved state and offers Settings as the recovery path. `CLLocationTracker.requestAuthorization()` returns `LocationAuthorization` once the user answers (continuation-driven via `locationManagerDidChangeAuthorization`). A constructor-injected `zoneStateSink` callback is invoked on every `ZoneState` transition — `SrednaBGApp` wires this to `LiveActivityManager.update(state:)` so the Live Activity is what convinces iOS to keep the process resident through a drive (the single biggest fix for "GPS stopped while screen was locked"). The service also tracks `lastActivityDate` (reset on tracking start and on every `ZoneState` case transition) and runs a 60 s fallback `Task` plus an on-fix check inside `process(point:)` — when `SettingsStore.autoStopHours * 3600` (or the DEBUG-only `debugAutoStopSeconds` override) elapses, `stop()` fires automatically so a forgotten-in-background session doesn't drain the battery.
- **SrednaBGMapCore** — MapLibre plumbing shared by SrednaBGUI and SrednaBGCarPlay. Owns `LocalTileServer` (`Network.framework` loopback HTTP/1.1 on `http://127.0.0.1:<ephemeral>`), `MBTilesReader` (sqlite3 actor, gzipped MVT out), `StyleRewriter` (substitutes `{MBTILES_URI}` / `{GLYPHS_URI}` / `{SPRITE_URI}` and rewrites `"url": "mbtiles://..."` vector sources into `tiles: [<local-server>]`), `MapLayers` (sources + layers for zones / endpoints / user arrow on `MLNStyle`), `MapUserArrow` (SF Symbol → UIImage), `BearingDamper` (freezes heading below 5 km/h to match Android's `BEARING_MIN_SPEED_KMH`), and `statusUIColor(_ Int32) -> UIColor` (UIKit peer for the SrednaBGTheme `Color` palette).
- **SrednaBGTheme** — shared visual palette + reusable badge. `Theme.statusGreen / .statusAmber / .statusRed` are the SwiftUI `Color` half of the traffic-light palette (Android-matched, with a dark-mode-aware amber); `statusSwiftUIColor(_ Int32) -> Color` bridges the packed `Int32` produced by `SrednaBGCore.zoneStatusColor`. `LimitBadge` is the round white badge with a red border (the iconic Bulgarian speed-limit glyph) shared by the in-app HUD chip and the Lock Screen / Dynamic Island Live Activity, so the visual stays identical across surfaces. SwiftUI-only; depends on `SrednaBGCore`. SrednaBGUI re-exports it (`@_exported import SrednaBGTheme`) so existing call sites keep working.
- **SrednaBGUI** — SwiftUI. `MapLibreView` is a `UIViewRepresentable` over `MLNMapView` from `SrednaBGMapCore` (tile server + layers + damper). `RootView` is the `TabView` the Xcode app shell instantiates and applies `keepScreenAwake(while: tracking.isTracking)` (in `KeepScreenAwakeModifier.swift`) — toggles `UIApplication.isIdleTimerDisabled` and re-asserts the value on `.active` because iOS resets the flag whenever the app is backgrounded. `HomeScreen` shows a permission card whenever `tracking.permission` is `.whenInUse` or `.denied` (Open Settings deep link via `UIApplication.openSettingsURLString`); the Start button retitles to "Try again" in that state. `.task` + `.onChange(of: scenePhase)` pump `tracking.refreshPermission()` so flipping permission in Settings clears the card on return. `Theme.swift` here is a thin re-export of `SrednaBGTheme`; the palette itself lives in that package so the Widget extension / CarPlay can pull colors without dragging in all of SrednaBGUI.
- **SrednaBGCarPlay** — `CarPlaySceneDelegate` (marked `@objc(CarPlaySceneDelegate)` so Info.plist resolves by bare ObjC name), `CarPlaySceneCoordinator` (owns `CPMapTemplate` + `CPNavigationSession`, runs a self-rearming `withObservationTracking` loop over `ZoneTrackingService` + `SettingsStore`), `CarPlayMapViewController` (UIKit port of `MapLibreView.Coordinator` — delegate class is non-isolated `@unchecked Sendable` with `MainActor.assumeIsolated` bodies to dodge the `unsafeForcedSync` hop), `CarPlaySpeedOverlayView` (UIKit HUD, hero ≥96pt, label ≥36pt per AA legibility floors), `CarPlaySpeedOverlayModel` (pure-logic projection, macOS-testable), `CarPlayLabels` / `CarPlayServiceBundle` / `CarPlayModule` (registry the `SrednaBGApp.init()` populates — iOS builds the scene delegate by class name so constructor DI isn't possible). Match Android Auto's minimal action strip: mute + zoom +/- + heading toggle; no CarPlay settings screen.

BG/EN `Localizable.xcstrings`, app icon, linted with SwiftLint (`ios/.swiftlint.yml`, enforced as a build phase in `SrednaBG.xcodeproj`).

## Build commands

```bash
# Swift 6, Xcode 16+ / toolchain ≥6.0; runs on macOS or Linux for Core
cd ios && swift build                    # Build all SPM packages
cd ios && swift test                     # Swift Testing cases across all packages
cd ios && swiftlint --strict             # Lint (config at ios/.swiftlint.yml)
cd ios && xcodebuild -scheme SrednaBG -project SrednaBG.xcodeproj \
    -destination 'generic/platform=iOS Simulator' -configuration Debug build \
    CODE_SIGNING_ALLOWED=NO              # App-shell build — SwiftLint runs as a build phase
```

## Definition of done

**An iOS task is not complete until both of these pass without error, from `ios/`:**

1. `swiftlint --strict` — exits 0, no warnings (strict mode promotes warnings to failures). Config lives at `ios/.swiftlint.yml`; a `SwiftLint` Run Script phase in `SrednaBG.xcodeproj` enforces the same invariant during Xcode builds.
2. `swift test` — all Swift Testing cases across the SPM packages pass. For changes that touch the app shell (Xcode-only sources, resources, build phases), also run `xcodebuild … -scheme SrednaBG … build` to confirm the app target still compiles.

Do not mark iOS work done when either check is red. If SwiftLint flags something and the rule is genuinely wrong for this codebase, narrow-disable it in `.swiftlint.yml` (with a comment explaining why) or add a file-level `// swiftlint:disable <rule>` with a matching `enable` — don't leave blanket disables.

## Offline map bundle (iOS side)

Produced by `backend/scripts/build-map-bundle.sh` — see `backend/CLAUDE.md` for the build pipeline.

- **Stage**: the `Map Bundle` Run Script phase in `ios/SrednaBG.xcodeproj` enforces bundle presence via `set -euo pipefail` + explicit file-presence checks (mirrors the Android `validateMapBundle` guard). `ios/SrednaBG/App/Resources/OfflineMap/` is gitignored.
- **Install** (`OfflineMapInstaller` / ZIPFoundation): extracts + atomically swaps the offline map bundle and rewrites `style.json` placeholders to bare `mbtiles://<abs-path>` — **no `{z}/{x}/{y}`** (same MapLibre `MBTilesFileSource` hazard as Android).
- **Sync — currently feature-gated OFF.** Client paths (`runMapSync`, `BackgroundSyncScheduler.scheduleMapSync`, `SyncClient.downloadMapBundle`, debug `/sync?action=map`) are wired but the production backend (`srednabg.com/api/*`) does not yet serve `/api/map/bundle.zip` or populate `map_hash` — the Namecheap scraper cron only emits zones, and the `backend/` Docker stack is dev/Mac-Mini-only. `FeatureFlags.isMapSyncEnabled` in `SrednaBGData/QAFlags.swift` is hardcoded `false` across all build flavors. **Re-enable** by flipping the constant to `true` after the backend bundle pipeline is live and the round-trip has been QA'd; mirrors `FeatureFlags.IS_MAP_SYNC_ENABLED` on Android.

## Key files

- **Core**: `ios/Package.swift`, `ios/Packages/SrednaBGCore/Sources/SrednaBGCore/{Models,VehicleType,GeoUtils,RoadMatcher,AverageSpeedCalc,GpsFilter,ZoneDetector,ZoneStatusColor}.swift`. Tests in `Tests/SrednaBGCoreTests/` use Swift Testing (`import Testing`, `@Test`, `#expect`); fixtures in `Tests/SrednaBGCoreTests/Resources/` (mirrored from `android/core/src/test/resources/`).
- **Data**: `ios/Packages/SrednaBGData/Sources/SrednaBGData/{ApiTypes,BackendURLs,SyncClient,SyncResult,SettingsKey,SettingsStore,BundledZonesLoader,ZoneStore,OfflineMapInstaller}.swift`.
- **Tracking**: `ios/Packages/SrednaBGTracking/Sources/SrednaBGTracking/{TtsPhrases,AnnouncementPolicy,AdaptiveLocationCadence,BearingFallback,GpsPointBuilder,LocationProviding,TTSEngine,CLLocationTracker,AVSpeechTTSEngine,AudioAlertManager,ZoneTrackingService,BackgroundSyncScheduler,LiveActivityManager}.swift`. `ZoneTrackingServicePermissionTests.swift` covers the two-step authorization gate with a scripted `LocationProviding` actor.
- **MapCore**: `ios/Packages/SrednaBGMapCore/Sources/SrednaBGMapCore/{LocalTileServer,MBTilesReader,StyleRewriter,MapLayers,MapUserArrow,BearingDamper,Theme+UIColor}.swift`.
- **Theme**: `ios/Packages/SrednaBGTheme/Sources/SrednaBGTheme/{Theme,LimitBadge}.swift`.
- **UI**: `ios/Packages/SrednaBGUI/Sources/SrednaBGUI/{Theme,L10n,Components/{SpeedDisplay,StatusChip},Screens/{HomeScreen,SettingsScreen,AboutScreen,ZoneMapScreen,RootView,KeepScreenAwakeModifier},Map/MapLibreView}.swift` (the local `Theme.swift` is a one-line re-export of `SrednaBGTheme`).
- **CarPlay** (package compiles + tests run; **not linked into the app target until the entitlement grant lands**): `ios/Packages/SrednaBGCarPlay/Sources/SrednaBGCarPlay/{CarPlayEntry,CarPlayLabels,CarPlaySpeedOverlayModel,CarPlaySpeedOverlayView,CarPlayMapViewController,CarPlaySceneCoordinator,CarPlaySceneDelegate}.swift`.
- **App shell**: `ios/SrednaBG/Info.plist` (no `UIApplicationSceneManifest` override — SwiftUI auto-generates a phone-only scene) + `ios/SrednaBG/App/SrednaBGApp.swift` (no CarPlay wiring) + `ios/SrednaBG/SrednaBG.entitlements` (kept in repo as a documentation artifact, **not** wired via `CODE_SIGN_ENTITLEMENTS`).

## QA debug surface (Debug builds only)

The QA harness (`qa/`) drives the booted iOS Simulator via `xcrun simctl` and a loopback HTTP debug listener bound by the app at launch. All of the below is gated `#if DEBUG` so release builds carry none of it.

- **Loopback HTTP control** — `DebugControlServer` (`SrednaBGData/DebugControlServer.swift`) binds to `127.0.0.1:<port>` on app launch in Debug builds; `DebugActionRouter` (`SrednaBGData/DebugActionRouter.swift`) dispatches `/ping`, `/setting?key=K&value=V`, `/sync?action=zones|map`, `/tracking?action=start|stop`, `/mute?on=1`, `/network?offline=1`. The HTTP form replaces the older `srednabg-debug://` URL scheme — `simctl openurl` raised an "Open in <App>" confirmation dialog on every dispatch that made automated QA unusable.
- **Structured `os_log` emitters** under subsystem `com.demosten.srednabg`, exposed by `QALog` (`ios/Packages/SrednaBGData/Sources/SrednaBGData/QALog.swift`). Categories `SrednaBG.Loc`, `SrednaBG.TTS`, `DebugSync`, `DebugSettings` use line bodies identical to the Android logcat tripwires (`onLocation: lat=…`, `onZoneStateChanged prev=…`, `speak: "…"`, `… -> SyncResult.…`, `set key=value`) so `qa/parsers.py` works unchanged. All interpolated values use `.public` privacy markers — `--style ndjson` would otherwise emit `<private>`.
- **Mute / offline** toggles back `QAFlags.ttsMuted` / `QAFlags.networkOffline` (`SrednaBGData/QAFlags.swift`). `AVSpeechTTSEngine.speak` drops calls when muted but the `speak:` log line still fires (parser self-test stays alive). `DebugActionRouter` short-circuits `/sync` to `Failed(offline)` when offline.
- **Sync hook**: `DebugSyncHook` (`SrednaBGData/DebugSyncHook.swift`) emits the QA-shaped `DebugSync` log line for each sync attempt's outcome. When `FeatureFlags.isMapSyncEnabled` is `false`, `/sync?action=map` short-circuits in `DebugActionRouter` with `... SYNC_MAP -> Skipped (feature disabled)` instead of invoking the handler — `qa/scenarios/sync/map_disabled.py` asserts on this shape as the regression tripwire.
- **Accessibility identifiers** on `HomeScreen` (`home-not-tracking-card`, `home-outside-card`, `home-in-zone-card`, `home-exiting-card`, `home-permission-card`, `home-start-stop`, `home-speed-display`), `SettingsScreen` (`settings-voice-enabled`, `settings-periodic-voice-updates`, `settings-announce-only-when-over`, `settings-app-language`, `settings-vehicle-type`, `settings-auto-stop-hours`, `settings-map-heading-up`, `settings-map-theme`, `settings-sync-now`), and `RootView` tabs (`tab-home`, `tab-map`, `tab-settings`). Consumed by the harness's `mobile-mcp` UI driver.

Invoke from the repo root with the booted simulator and a Debug build installed:

```bash
python qa/srednabg_qa.py --suite smoke --platform ios
```

See `qa/CLAUDE.md` for the full suite list and platform caveats.

## Remaining work

### Phase 8c — Phone-only App Store release

CarPlay is intentionally unwired from the app target for the first release. The phone build ships first; CarPlay re-enables once Apple grants the entitlement (see "Re-enabling CarPlay" below).

- **Privacy manifest**: add `ios/SrednaBG/PrivacyInfo.xcprivacy` declaring `NSPrivacyTracking = false`, an empty `NSPrivacyCollectedDataTypes` array, and `NSPrivacyAccessedAPITypes` reasons for `UserDefaults` (`CA92.1`), file timestamp (`C617.1`) if used. MapLibre + ZIPFoundation already ship their own.
- **App Store metadata** (BG primary, EN secondary): name `SrednaBG`, subtitle (≤30 char) `Секционен контрол`, promotional text, description, keywords (mirror `android/CLAUDE.md` line 80), Support URL + Privacy Policy URL pointing at `srednabg.com`, category Navigation primary / Travel secondary.
- **Screenshots**: 6.9" iPhone (1320×2868), 6.5" iPhone (1284×2778), 13" iPad (2064×2752 — `TARGETED_DEVICE_FAMILY = "1,2"`). Capture from Simulator running the app.
- **Version bump**: `MARKETING_VERSION` is `0.1.0` — bump to `1.0.0` for first TestFlight build. `CURRENT_PROJECT_VERSION` increments per upload.
- **First TestFlight upload**: `Product → Archive` → Organizer → Distribute → App Store Connect. Beta App Review takes <24h for first build.

### Phase 8b — CarPlay re-enable (post-grant)

`com.apple.developer.carplay-navigation` is on iOS 18+ Simulator's restricted-entitlement allow-list. With it embedded but un-granted, `amfi` rejects the spawn with POSIX 163 / `Launchd job spawn failed`. With it stripped, iOS doesn't activate the `CPTemplateApplicationScene`. There's no developer-side workaround — both Simulator and device CarPlay testing are blocked on Apple's grant. File the request at https://developer.apple.com/contact/carplay/ once the phone TestFlight build exists.

When the grant lands, re-wire CarPlay (each step independent — git revert of the deferral commit also works):

1. **Add `CODE_SIGN_ENTITLEMENTS = SrednaBG/SrednaBG.entitlements;`** to both Debug and Release in `project.pbxproj`. Automatic signing then refreshes the provisioning profile to include the granted entitlement.
2. **Add the scene manifest** to `ios/SrednaBG/Info.plist` (set `INFOPLIST_KEY_UIApplicationSceneManifest_Generation = NO` in both configs and add a `UIApplicationSceneManifest` dict declaring both `UIWindowSceneSessionRoleApplication` and `CPTemplateApplicationSceneSessionRoleApplication` — the second points `UISceneDelegateClassName` at the bare ObjC name `CarPlaySceneDelegate`, the first has no delegate so SwiftUI handles it).
3. **Re-link `SrednaBGCarPlay`** into the SrednaBG target: add a `PBXBuildFile` entry, a `XCSwiftPackageProductDependency` entry, and references in both `packageProductDependencies` and the `PBXFrameworksBuildPhase` files list (twin pattern of the existing `SrednaBGMapCore` entries).
4. **Re-add the runtime wiring** in `ios/SrednaBG/App/SrednaBGApp.swift` — `import SrednaBGCarPlay` + a `CarPlayModule.configure(CarPlayServiceBundle(...))` call inside `init()` under `#if canImport(CarPlay)`, with a `labelsProvider` closure that resolves `L10n.*` strings.
5. **Verify in Xcode's CarPlay Simulator** (`I/O → External Displays → CarPlay`): SrednaBG appears in the launcher, the offline map renders, overlay flips Outside → InZone as simulated location crosses a zone, heading-up / mute toggles propagate to the phone map tab via the shared `SettingsStore`.
