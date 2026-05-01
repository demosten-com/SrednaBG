# SrednaBG iOS

iOS phone port of SrednaBG. Phase 8 (see top-level `CLAUDE.md`). CarPlay target is in-tree as WIP — code-complete but unwired pending Apple's entitlement, not part of the initial release.

## Status

- **Phase 8a — Phone MVP**: Core + Data + Tracking + UI packages are written and tested. App shell sources (`App/`) ready to drop into an Xcode project. Remaining: create the Xcode project, integrate MapLibre Native iOS for the map view, ship to TestFlight.
- **Phase 8b — CarPlay**: Gated on Apple's `com.apple.developer.carplay-navigation` entitlement (file early in 8a; Apple manual review ~2–6 weeks).
- **Phase 8c — Release prep**: TestFlight + App Store submission.

## Layout

```
ios/
  Package.swift                 SwiftPM manifest, Swift 6 mode, strict concurrency
  App/                          App shell sources (drop into an Xcode project)
    SrednaBGApp.swift           @main entry — composes all packages
    Resources/                  optional offline-map staging (gitignored)
  Packages/
    SrednaBGCore/               Pure-Swift port of ../android/core/  — zero deps  (8 src + 8 test files, 92 tests)
    SrednaBGData/               URLSession + JSON cache + UserDefaults    (9 src + 6 test files, 19 tests)
    SrednaBGTracking/           CoreLocation + AVSpeechSynthesizer +
                                 ActivityKit + BGTaskScheduler            (13 src + 6 test files, 35 tests)
    SrednaBGUI/                 SwiftUI screens + components                (9 src + 2 test files, 10 tests)
```

156 tests across 22 suites green via `swift test`. iOS Simulator build green via `xcodebuild`.

## Build & test

Requires Xcode 16+ (Swift 6.0+ toolchain) on macOS.

```bash
cd ios
swift build                                                                # builds 4 packages on macOS
swift test                                                                 # runs all 156 tests
xcodebuild -scheme SrednaBG-Package -destination 'generic/platform=iOS Simulator' build
                                                                           # verifies iOS-only files compile
```

## Wiring up the app shell

The `App/` directory holds source for the thin Xcode app target. SwiftPM
can't produce a `.app` directly — Xcode must wrap the four packages.

1. **Create a new Xcode iOS App project**: `Product → New Project → iOS App`,
   product name `SrednaBG`, interface SwiftUI, language Swift, in
   `ios/SrednaBG.xcodeproj`. Choose iOS 17 deployment target. Leave
   `Generate Info.plist File` checked (Xcode default since 13) — we drive
   everything via Build Settings, no manual `Info.plist` needed.
2. **Replace the auto-generated app entry**: delete the generated
   `SrednaBGApp.swift` + `ContentView.swift`; add `App/SrednaBGApp.swift`
   to the target.
3. **Add the local SwiftPM packages**: `File → Add Package Dependencies →
   Add Local`, point at `ios/`. Then in the app target's "General →
   Frameworks, Libraries, and Embedded Content", add `SrednaBGCore`,
   `SrednaBGData`, `SrednaBGTracking`, `SrednaBGUI`.
4. **Apply Info.plist build settings.** Paste the block below into the
   target's `Build Settings` (or, equivalently, paste the matching keys
   into the target's "Info" tab — Xcode stores both in `.pbxproj`). All
   `INFOPLIST_KEY_*` arrays are space-separated; multi-word strings need
   quoting.

   ```text
   GENERATE_INFOPLIST_FILE = YES
   CURRENT_PROJECT_VERSION = 1
   MARKETING_VERSION = 0.1.0

   # User-facing copy. App Review enforces value-to-driver wording, not
   # tech rationale — that's why both strings explain the dash-mounted
   # background-tracking use case.
   INFOPLIST_KEY_NSLocationAlwaysAndWhenInUseUsageDescription = "SrednaBG tracks your average speed inside Bulgarian section-control camera zones — even when the app is in the background or the screen is off — so it can warn you before the camera fines you."
   INFOPLIST_KEY_NSLocationWhenInUseUsageDescription = "SrednaBG needs your location to know which section-control zone you're entering and to compute your running average speed."

   # Background modes: location for CLLocationManager, audio for
   # AVSpeechSynthesizer with the screen off, fetch + processing for the
   # two BGTaskScheduler tasks (zone sync + map sync).
   INFOPLIST_KEY_UIBackgroundModes = location audio fetch processing

   # ActivityKit Live Activity for in-zone Lock Screen / Dynamic Island.
   INFOPLIST_KEY_NSSupportsLiveActivities = YES

   # Localization: BG default, EN fallback. Mirror values/values-en from
   # the Android resource layout.
   INFOPLIST_KEY_CFBundleLocalizations = bg en
   INFOPLIST_KEY_CFBundleDevelopmentRegion = bg

   # Orientation.
   INFOPLIST_KEY_UISupportedInterfaceOrientations_iPhone = UIInterfaceOrientationPortrait UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight
   ```

5. **Add `BGTaskSchedulerPermittedIdentifiers`** — this is the one key
   without an `INFOPLIST_KEY_*` shortcut. In the target's "Info" tab,
   click `+` to add a custom property:
   - Key: `BGTaskSchedulerPermittedIdentifiers`
   - Type: Array
   - Items: `com.demosten.srednabg.zonesync`, `com.demosten.srednabg.mapsync`
     (must match the constants in
     `SrednaBGTracking/BackgroundSyncScheduler.swift`)
6. **Stage the offline map bundle** (optional, sized to fit the IPA):
   add a Run Script Build Phase before "Compile Sources":
   ```bash
   if [ -d "${SRCROOT}/../backend/data/map-bundle" ]; then
     mkdir -p "${SRCROOT}/App/Resources/OfflineMap"
     rsync -a --delete "${SRCROOT}/../backend/data/map-bundle/" "${SRCROOT}/App/Resources/OfflineMap/"
   fi
   ```
   Then add `App/Resources/OfflineMap/` as a folder reference (blue) in the
   target so the contents ship inside the app bundle.
7. **Localizable strings**: add an empty `Localizable.xcstrings` to the
   target. The 72 strings will populate as Xcode auto-extracts from the
   `L10n.*` calls in `SrednaBGUI`. Mirror translations from
   `android/app/src/main/res/values/strings.xml` (BG default) and
   `values-en/strings.xml` (English fallback).
8. **MapLibre integration** (Phase-8a follow-up): add
   `https://github.com/maplibre/maplibre-gl-native-distribution` as a SPM
   dependency on the app target (or on `SrednaBGUI` directly), then
   replace the `Rectangle` placeholder in `Screens/ZoneMapScreen.swift`
   with a `UIViewRepresentable` wrapping `MLNMapView`.
9. **Entitlements** (deferred): no entitlement file is needed for Phase 8a.
   Live Activities require only the `NSSupportsLiveActivities` Info.plist
   key set above. For Phase 8b, Xcode will create
   `SrednaBG.entitlements` automatically when you add the
   `com.apple.developer.carplay-navigation` capability after Apple grants it.

After this, ⌘R on an iPhone simulator should boot to the Home tab; tapping
"Start tracking" requests Always location and begins consuming
`CLLocationManager` updates through the `ZoneTrackingService`.

## Locked-in decisions

- Hand-port `android/core/` to Swift (no Kotlin Multiplatform).
- iOS 17 minimum, Swift 6 strict concurrency.
- MapLibre Native iOS for map rendering, served via an in-process tile HTTP
  server (`mbtiles://<abs-path>` placeholders match Android byte-for-byte).
- Plain JSON-on-disk for zones (`ZoneStore` actor) — SwiftData was overkill
  for a tiny read-heavy dataset queried per GPS tick.
- UserDefaults for the 8 settings keys (key names match Android exactly so
  the QA harness's `DebugControlReceiver` analogue can be reused).
- ActivityKit for in-zone Lock Screen / Dynamic Island status.
- iOS `ZoneDetector.update(_:vehicleType:)` honors the user's vehicle-type
  setting; Android currently hardcodes `.car` (TODO to backport — tracked
  in top-level `CLAUDE.md` Remaining Work).
