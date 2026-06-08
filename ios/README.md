# SrednaBG iOS

iOS phone port of SrednaBG. Phase 8 (see top-level `CLAUDE.md`). CarPlay
target is in-tree as WIP — code-complete but unwired pending Apple's
entitlement, not part of the initial release.

## Status

- **Phase 8a — Phone MVP**: Done. SwiftPM packages, the Xcode app shell
  (`ios/SrednaBG.xcodeproj/`), MapLibre Native via `SrednaBGMapCore`, Live
  Activity / Dynamic Island, and permission gating are all wired.
- **Phase 8b — CarPlay**: Gated on Apple's
  `com.apple.developer.carplay-navigation` entitlement. Package compiles +
  tests run; **unwired from the SrednaBG app target** until the grant lands.
  Re-link path documented in `ios/CLAUDE.md` "Remaining work".
- **Phase 8c — Release prep**: Privacy manifest, App Store metadata +
  screenshots, TestFlight, App Store submission. CarPlay entitlement is
  filed once the first TestFlight build exists.

## Layout

```
ios/
  Package.swift                 SwiftPM manifest, Swift 6 mode, strict concurrency
  SrednaBG.xcodeproj/           Xcode app shell (wraps the SPM packages)
  SrednaBG/                     App-shell sources, Info.plist, entitlements doc
    App/                        @main entry + debug HTTP listener
    Resources/OfflineMap/       Staged map bundle (gitignored, built by a Run Script phase)
  Packages/
    SrednaBGCore/               Pure-Swift port of ../android/core/ — zero deps
    SrednaBGData/               URLSession + JSON cache + UserDefaults + debug-control router
    SrednaBGTracking/           CoreLocation + AVSpeechSynthesizer + ActivityKit + BGTaskScheduler
    SrednaBGMapCore/            MapLibre + local tile HTTP server + MBTiles reader (shared by UI + CarPlay)
    SrednaBGTheme/              Status-color palette + reusable LimitBadge component
    SrednaBGUI/                 SwiftUI screens + components (re-exports SrednaBGTheme)
    SrednaBGCarPlay/            CPMapTemplate + CPNavigationSession scene (unwired from app target)
```

Swift Testing suite green via `swift test` across all packages.
iOS Simulator build green via `xcodebuild` (Debug + Release with clean
Automatic signing) for the SrednaBG app target.

## Build & test

Requires Xcode 16+ (Swift 6.0+ toolchain) on macOS.

```bash
cd ios
swift build                    # Build all SPM packages
swift test                     # Run the full Swift Testing suite
swiftlint --strict             # Lint (config at ios/.swiftlint.yml)
xcodebuild -scheme SrednaBG -project SrednaBG.xcodeproj \
    -destination 'generic/platform=iOS Simulator' -configuration Debug build \
    CODE_SIGNING_ALLOWED=NO    # App-shell build (SwiftLint runs as a build phase)
```

`ios/CLAUDE.md` has the per-package map, the QA debug surface, the
offline-map-bundle pipeline, and the CarPlay re-link checklist.

## Locked-in decisions

- Hand-port `android/core/` to Swift (no Kotlin Multiplatform).
- iOS 17 minimum, Swift 6 strict concurrency.
- MapLibre Native iOS for map rendering, served via an in-process tile HTTP
  server (`mbtiles://<abs-path>` placeholders match Android byte-for-byte).
- Plain JSON-on-disk for zones (`ZoneStore` actor) — SwiftData was overkill
  for a tiny read-heavy dataset queried per GPS tick.
- UserDefaults for the user-tunable settings keys — alert threshold, voice
  toggles, language, vehicle type, map heading-up, map theme, and the
  inactivity auto-stop window (`auto_stop_hours`, default 3h). Key names
  match Android exactly so the QA harness's `DebugControlReceiver`
  analogue can be reused.
- ActivityKit for in-zone Lock Screen / Dynamic Island status.
- `VehicleType` (car / truck / bus / motorcycle) with a per-vehicle speed
  limit, exposed in Settings; `ZoneDetector.update(_:vehicleType:)` and the
  Kotlin core are at parity (both honor the setting).
- Zone data ships from the single source of truth `backend/data/zones.json`,
  copied into the app at build time by the `Bundled Zones` Run Script phase
  (the same file Android bundles).
- TTS via `AVSpeechSynthesizer`: pure `AnnouncementPolicy.decide` owns the
  announce/suppress matrix (entry / over-limit / recovered / exit / periodic,
  co-located-camera entry); `AVSpeechTTSEngine` drives the `AVAudioSession`
  (`.playback` + `.duckOthers`, `audio` background mode) so guidance keeps
  speaking screen-off. See `ios/CLAUDE.md` for the background-audio rationale.
