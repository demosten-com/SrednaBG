# qa/

End-to-end QA harness (Python, stdlib + PyYAML). Drives the running Android emulator (via `adb`) **or** a booted iOS Simulator (via `xcrun simctl` + a loopback HTTP debug listener the iOS app binds at launch in Debug builds). Parses typed events from the platform's log stream, asserts on the full app stack (zone state machine, audio alerts, settings, sync, UI). Pairs with the JVM / Swift unit tests — units cover algorithm math, this covers everything they don't.

## Architecture

- `qa/srednabg_qa.py` — entry point / orchestrator. Picks the backend via `--platform {auto,android,ios}`.
- `qa/device.py` — `Device` ABC + `current()` / `set_current()` singleton. The runner, scenarios, settings/sync helpers, and drive pump all go through this facade.
- `qa/devices/android.py` — `AndroidDevice` (delegates to `qa/adb.py`).
- `qa/devices/ios.py` — `IosDevice` (wraps `xcrun simctl` + HTTP POSTs to the app's loopback debug listener). iOS-only; requires macOS.
- `qa/devices/{android_log,ios_log}.py` — `LogObserver` subclasses (logcat threadtime / `simctl spawn booted log stream --style ndjson`).
- `qa/parsers.py` — shared regex set + `parse_message(tag, msg, raw)`. Same tag names (`SrednaBG.Loc`, `SrednaBG.TTS`, `DebugSync`, `DebugSettings`) on both platforms.
- `qa/log_observer.py` — abstract observer with `for_current_device()` factory.
- `qa/adb.py` — shells out to `adb` (Android-only). Kept as the Android backend library.
- `qa/events.py` — typed event dataclasses (platform-agnostic).
- `qa/drive.py` — parses GPX into a `DrivePlan`, pumps `device.geo_fix()` at the right cadence.
- `qa/assertions.py` — `expect` / `expect_in_order` / `expect_never` over the event queue.
- `qa/runner.py` — runs ordered scenario steps with per-scenario log-buffer isolation.
- `qa/settings.py` — flips settings via the active device (broadcast on Android, HTTP POST to the debug listener on iOS).
- `qa/sync.py` — triggers sync via the active device and inspects on-disk map bundle integrity.
- `qa/ui.py`, `qa/report.py` — UI walk + report generation.
- Scenarios under `qa/scenarios/{bulk,representative,edge,sync,ui}/`.
- Fixtures in `qa/fixtures/` (`tts_phrases.yaml`, GPX).
- `qa/logcat.py` — compatibility shim, re-exports `LogObserver as LogcatObserver` and the regexes. New code should import from `qa.log_observer` + `qa.parsers`.

Android depends on `android/`'s debug-only `DebugSyncReceiver` and `DebugControlReceiver`. iOS depends on the Debug-only loopback HTTP debug listener (`DebugControlServer` + `DebugActionRouter` in `SrednaBGData`) plus `QALog` + `DebugSyncHook` (see `ios/SrednaBG/App/SrednaBGApp+DebugServer.swift`, `ios/Packages/SrednaBGData/Sources/SrednaBGData/QALog.swift`). The earlier `srednabg-debug://` URL-scheme dispatch was replaced because `simctl openurl` raised an "Open in <App>" confirmation dialog on every dispatch — see `ios/CLAUDE.md` "QA debug surface" for the current shape.

## Suite invocations

### Android (default; debug APK installed on the running emulator)

```bash
python qa/srednabg_qa.py --suite smoke           # ~5 min — 1 zone + 1 sync + parser self-test
python qa/srednabg_qa.py --suite representative  # ~30 min — 6 hand-picked zones × 4 settings combos + sync set
python qa/srednabg_qa.py --suite scenarios       # ~20 min — 7 edge cases (stop, dropout, off-ramp, U-turn, swap, …)
python qa/srednabg_qa.py --suite sync            # ~5 min — zones happy + offline; map happy + integrity
python qa/srednabg_qa.py --suite ui              # <1 min — phone UI walk
python qa/srednabg_qa.py --suite full-zones      # ~75 min @4× — all 72 zones, minimal asserts
python qa/srednabg_qa.py --suite nightly         # ~2 hr — representative + full-zones + scenarios + ui
```

### iOS Simulator (macOS only; Debug build installed in a booted simulator)

```bash
# Prereqs:
#   1. xcrun simctl boot <udid>  # or open Simulator.app
#   2. xcodebuild ... -configuration Debug build install — Debug, not Release;
#      the loopback debug HTTP listener + QA log emitters are #if DEBUG.
#   3. xcrun simctl install booted <path-to-built-.app>

python qa/srednabg_qa.py --suite smoke           --platform ios
python qa/srednabg_qa.py --suite representative  --platform ios
# scenarios/sync/ui/nightly likewise — same suite names, just add --platform ios
```

`--platform auto` (default) picks adb when an emulator is attached, else iOS Simulator on macOS, else errors out.

#### iOS-specific caveats

- **Headless on a Mac mini**: the iOS Simulator needs an active GUI session (Metal rendering). No workaround.
- **TTS muting**: there's no OS-level mute toggle on the simulator. The harness's `mute_audio()` POSTs `/mute?on=1` to the debug listener, which swaps the `AVSpeechTTSEngine` for a no-op while still emitting `speak:` log lines (so the parser self-test still trips on broken phrase changes).
- **Network offline**: `simctl status_bar` doesn't actually gate the network. `IosDevice.go_offline()` flips a `QAFlags.networkOffline` UserDefaults flag that makes the `DebugActionRouter` short-circuit sync requests to `Failed`. Observable behavior matches Android's airplane-mode path.
- **Mid-route GPS mutation**: `simctl location set` per-point is slower than `adb emu geo fix` (≈100–500 ms vs <10 ms). The steady-cruise suites (smoke / representative / full-zones) run fine on it; edge scenarios that fan out fixes rapidly (`gps_dropout`, `wrong_direction`, `u_turn`, `vehicle_swap`) are still Android-only until a faster iOS pump lands.

Reports land in `qa/reports/<suite>-<timestamp>/` (`junit.xml` + `summary.md` + `screenshots/`); exit code 0 = all passed. Invoke from a Claude Code session with the `/qa-app` skill — it runs the orchestrator, parses the report, and summarizes back in <200 words.

## Adding scenarios

- YAML for "drive zone X at speed Y" variations.
- Python under `qa/scenarios/edge/` for mid-trip changes (dropout, U-turn, etc.) — register the module in `EDGE_SCENARIOS` in `qa/srednabg_qa.py`.
- Use `device.current().geo_fix(...)` and `qa.settings` / `qa.sync` (not `qa.adb` directly) so the scenario runs on both platforms.

## Map sync — feature-gated off

Both apps gate map sync behind `FeatureFlags.IS_MAP_SYNC_ENABLED` (Kotlin) / `FeatureFlags.isMapSyncEnabled` (Swift) until the production backend serves `/api/map/bundle.zip` + `map_hash`. While that's the case, `SYNC_MAP` returns `Skipped (feature disabled)` from both `DebugSyncReceiver` (Android) and `DebugActionRouter` (iOS).

`qa/scenarios/sync/map_disabled.py` triggers `SYNC_MAP` and asserts `outcome == Skipped` — this is the regression tripwire that catches accidental removal of either platform's gate. When the backend lights up and the flags flip, restore `qa/scenarios/sync/map_happy.py` (asserts `Updated`/`UpToDate` + on-disk integrity) and swap the entry in `SYNC_SCENARIOS` back. See `ios/CLAUDE.md` and `android/CLAUDE.md` for the gate-call-site map.

## Tripwire

When log line shapes change in either platform's app — `AudioAlertManager.kt` / `LocationTrackingService.kt` on Android, `QALog` + `ZoneTrackingService.swift` / `CLLocationTracker.swift` / `AudioAlertManager.swift` on iOS — the smoke suite's parser self-test fails loudly with a pointer to the affected line. Fix the regex in `qa/parsers.py` (the shared module) and both platforms re-converge.

## Store-screenshot tooling

Two orchestrators live alongside the QA harness — they share `qa/screenshots/loader.py` + `qa/screenshots/shots.yaml` but are otherwise independent of the suites above:

- `qa/srednabg_screenshots.py` — drives the running emulator / Simulator to capture the raw store PNGs. Skill: `/screenshot-app`.
- `qa/srednabg_frame_screenshots.py` — **offline** post-processor that composes Waze-style marketing frames (solid bg + centered title + smaller phone screenshot with rounded corners + thin black border) from the raw PNGs. Skill: `/frame-screenshots`. No emulator / Simulator involved.

### Outputs (gitignored)

Both write under `web/screenshots/`, which is in `.gitignore`:

- Raw: `web/screenshots/<platform>/NN-<platform>-<theme>-<lang>.png`
- Framed: `web/screenshots/<platform>/framed/NN-<theme>-<lang>.png`

Regenerate via the skills. Don't commit either tree — `web/CLAUDE.md` explains how the marketing site picks up the framed PNGs at deploy time.

### `qa/screenshots/shots.yaml`

Single source of truth for both scripts. Top-level keys:

- `zone_id`, `languages`, `shots:` — consumed by capture.
- `frame:` block + per-shot `background` / `title` — consumed only by framing. Capture ignores them. The renderer auto-shrinks oversized titles and supports a hard `\n` in title text; literal `#RRGGBB` works anywhere a palette key (from `frame.colors`) is accepted.
- `frame.chrome_mask.<platform>` — paints a solid band over the top of each raw screenshot before rounded-corner cropping, to hide the OS status bar. Color is sampled at render time from the bottom tab bar (uniform per theme). `top_px: 0` disables the mask for that platform.

### Python dependencies

`qa/requirements.txt` (PyYAML + Pillow ≥10). The QA harness itself is stdlib + PyYAML; Pillow is only needed for `/frame-screenshots`. Install with `pip install -r qa/requirements.txt` (per project preference: pip + `requirements.txt`, never `pyproject.toml`).

### Bundled font

`qa/screenshots/fonts/Nunito-Bold.ttf` ships with the repo (SIL OFL 1.1; license at `qa/screenshots/fonts/LICENSE-OFL.txt`) so framing works without a system-font hunt and Cyrillic renders correctly. Don't replace it with a non-OFL font.
