# SrednaBG (Средна БГ)

Free, open-source Android + iOS phone app for tracking average speed in Bulgaria's section control camera zones. Android Auto and CarPlay surfaces exist in the codebase as WIP and are not part of the initial release.

## Install

- F-Droid: <https://f-droid.org/packages/com.demosten.srednabg/> — recipe merged into `fdroiddata`; the app appears once F-Droid's build server publishes the first signed build.
- GitHub Releases: <https://github.com/demosten-com/SrednaBG/releases>

- **SourceCode:** <https://github.com/demosten-com/SrednaBG>
- **IssueTracker:** <https://github.com/demosten-com/SrednaBG/issues>
- **License:** [MIT](LICENSE)
- **Website:** <https://srednabg.com>

## Quick Start

```bash
# Android Gradle commands run from android/ (this folder is the Gradle root)

# Build everything
cd android && ./gradlew build

# Run core library tests
cd android && ./gradlew :core:test

# Run Android unit tests
cd android && ./gradlew :app:test

# Build debug APK
cd android && ./gradlew :app:assembleDebug

# Build release APK (R8 minified)
cd android && ./gradlew :app:assembleRelease

# Run Python scraper tests
cd scrapers && pip install -r requirements-dev.txt && python -m pytest

# Generate a drive-through GPX for emulator testing (defaults to AM Trakiya east @ 130 km/h)
cd scrapers && python scripts/make_test_route.py --out /tmp/route.gpx

# Build the offline map bundle (mbtiles z5–z12 + vendored style/glyphs) for the APK and sync endpoint
# Self-contained: pinned Planetiler JAR + Geofabrik OSM; needs Java 21+. Cleans up scratch.
bash backend/scripts/build-map-bundle.sh

# End-to-end QA harness against a running phone emulator (debug APK installed)
python qa/srednabg_qa.py --suite smoke           # ~5 min sanity pass
python qa/srednabg_qa.py --suite representative  # ~30 min — 6 zones × 4 settings combos + sync
python qa/srednabg_qa.py --suite scenarios       # ~20 min — edge cases (stop, dropout, off-ramp, U-turn, …)
python qa/srednabg_qa.py --suite nightly         # ~2 hr — everything
```

The Gradle build auto-stages `backend/data/map-bundle/` into `android/app/src/main/assets/map/` via the `prepareMapAssets` task, so a debug APK built after `build-map-bundle.sh` ships with a fully-offline map. If the bundle directory is absent the build still succeeds and the app falls back to the network style at runtime.

## Testing in an Emulator

The phone UI runs on any Pixel-class Google Play emulator. For the Android Auto surface (WIP, not shipped in the initial release — developer testing only), use an **Android Automotive OS (AAOS)** emulator image (Tools → Device Manager → Create Virtual Device → Automotive tab). Feed the app fake GPS by importing the GPX above in Extended Controls → Location → Routes. See `CLAUDE.md` → *Drive simulation* for details.

For repeatable end-to-end coverage, run the QA harness in `qa/` against a phone emulator with the debug APK installed — it drives `adb emu geo fix` from GPX plans, parses typed events from filtered logcat, and asserts on the full app stack (zones, audio, settings, sync, UI). See `qa/README.md`.

## Testing with DHU (Desktop Head Unit)

*The Android Auto surface is WIP and not part of the initial release; this section is for developer testing only.*

For iterating on the Android Auto UI on real hardware, the **Desktop Head Unit** projects your phone's AA output to a window on your Mac — faster than tethering a real car. DHU ships with Android Studio (Tools → SDK Manager → SDK Tools → *Android Auto Desktop Head Unit Emulator*).

```bash
# 1. Enable on the phone: Settings → Apps → Android Auto → Additional settings → Developer
#    settings → Head unit server, then tap the AA version banner 10× to unlock developer mode.
# 2. Connect phone via USB and tell it to start the DHU server:
adb forward tcp:5277 tcp:5277
adb shell am start -n com.google.android.projection.gearhead/com.google.android.apps.auto.carservice.HeadUnitStartupActivity

# 3. Launch DHU on the Mac:
"$ANDROID_HOME/extras/google/auto/desktop-head-unit"

# 4. Install the debug APK and open SrednaBG in the DHU dock.
cd android && ./gradlew :app:assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk
```

To drive the map without actually driving, the `scripts/feed_gpx.py` script injects GPX trackpoints straight into `LocationTrackingService` via a debug broadcast receiver — no mock-location app, no emulator required:

```bash
# Generate a route (see scripts/make_test_route.py --help for zone/speed flags)
python scrapers/scripts/make_test_route.py --out /tmp/route.gpx

# Real-time playback:
python scripts/feed_gpx.py /tmp/route.gpx

# Fast-forward (useful for covering a full zone in under a minute):
python scripts/feed_gpx.py /tmp/route.gpx --speed 10
```

The feeder auto-starts the foreground service, suppresses real FLP updates for 15 s after each injected point (so real GPS doesn't yank the dot back), and resumes real GPS automatically after the feed ends. The injected points show in logcat as `provider=debug-gpx mock=true`.

On iOS, `scripts/feed_gpx_ios.py` is the Simulator-side equivalent — it shells into `xcrun simctl location start` so `CLLocation.speed`/`course` come out interpolated the way real hardware emits them (no debug-broadcast hook is needed on iOS).

## Project Structure

- `android/` - Android phone app (Compose, MapLibre, Car App Library); the Android Auto target is WIP and dev-only — not in the initial release. The pure-Kotlin calculation engine lives at `android/core/`
- `scrapers/` - Python data pipeline for zone data
- `backend/` - Offline map-bundle builder (self-contained Planetiler JAR) + local zone-data staging
- `qa/` - End-to-end QA harness (drives the phone emulator via adb, asserts on logcat events)
- `ios/` - iOS phone app (Swift 6, SwiftUI, MapLibre Native) — SPM packages + Xcode shell, ships with the same offline map bundle. CarPlay package is code-complete but unwired (WIP, not in the initial release; pending Apple's `carplay-navigation` entitlement).

## Privacy

See [PRIVACY_POLICY.md](PRIVACY_POLICY.md). Location data is processed on-device only and never transmitted.

## Attribution

Map data: &copy; OpenMapTiles &copy; OpenStreetMap contributors (ODbL)
