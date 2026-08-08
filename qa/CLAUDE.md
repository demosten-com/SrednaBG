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
- `qa/drive.py` — parses GPX into a `DrivePlan`, pumps `device.feed_point()` at the right cadence with explicit per-fix speed + bearing (derived from the plan geometry) and `time_ms` stamps from the plan's sim timeline (`TrackPoint.sim_offset_ms`, preserved by `compressed()`). It deliberately does NOT use `geo_fix` — `adb emu geo fix` carries neither speed nor bearing, the emulator's GPS pipe delivers it late/bunched, and the app's inferred course then flips on the jumps, matching the opposite-carriageway sibling at a shared camera (the "arrow drives the zone backwards" artifact).
- `qa/assertions.py` — `expect` / `expect_in_order` / `expect_never` over the event queue.
- `qa/runner.py` — runs ordered scenario steps with per-scenario log-buffer isolation. `Scenario.timeout_s` is a hard wall: steps run on a worker thread; on expiry the runner sets the drive-abort flag (unblocks an in-flight `pump()` via `DriveAborted`), records the timeout with the stuck step's name, and moves on.
- Bulk/representative scenarios assert enter + exit, the YAML's `forbid_in_zone_rebound` (no re-entry of the **target** zone after its `Exiting` — the flap class; scoped to the target id because the synthetic straight-line approach/exit can legitimately clip a curved *adjacent* zone and flap within it, e.g. i4-04-east's approach across i4-03-east's tail), and optional `expect_avg_kmh` ± `avg_kmh_tolerance` (mean of in-zone `DisplaySpeed` events). Generated GPX fixtures under `qa/fixtures/gpx/` (gitignored) embed a content hash of the zone geometry + route params in the filename, so a zones.json change regenerates them automatically — no manual cache busting.
- `qa/settings.py` — flips settings via the active device (broadcast on Android, HTTP POST to the debug listener on iOS).
- `qa/sync.py` — triggers sync via the active device and inspects on-disk map bundle integrity.
- `qa/ui.py`, `qa/report.py` — UI walk + report generation.
- Scenarios under `qa/scenarios/{bulk,representative,edge,sync,history,ui}/`. The `history` package drives a zone then reads the History DB via the active device's `dump_history()` — a `DUMP_HISTORY` broadcast on Android, a `/history?action=dump` HTTP call on iOS — both emitting the identical `DUMP_HISTORY …` line on tag `DebugSettings` (parsed into a `HistoryDump` event). It's **cross-platform** (no `--platform` gate), registered in `HISTORY_SCENARIOS`. Separately, for *manual* browsing / store screenshots (not a suite step), both platforms expose a curated seed that wipes + refills the DB with varied sample traversals: Android's `SEED_HISTORY` broadcast (`--es count N`, see `android/CLAUDE.md`) and iOS's `/history?action=seed[&count=N]` (see `ios/CLAUDE.md`) — twin `HistorySeeder`s producing the same scenario set.
- Fixtures in `qa/fixtures/` (GPX). Harness unit tests in `qa/tests/` (parsers / geo / drive / speech-number + TTS phrase parity), run headlessly via `python -m unittest discover qa/tests`.
- `qa/logcat.py` — compatibility shim, re-exports `LogObserver as LogcatObserver` and the regexes. New code should import from `qa.log_observer` + `qa.parsers`.

Android depends on `android/`'s debug-only `DebugSyncReceiver` and `DebugControlReceiver`. iOS depends on the Debug-only loopback HTTP debug listener (`DebugControlServer` + `DebugActionRouter` in `SrednaBGData`) plus `QALog` + `DebugSyncHook` (see `ios/SrednaBG/App/SrednaBGApp+DebugServer.swift`, `ios/Packages/SrednaBGData/Sources/SrednaBGData/QALog.swift`). The earlier `srednabg-debug://` URL-scheme dispatch was replaced because `simctl openurl` raised an "Open in <App>" confirmation dialog on every dispatch — see `ios/CLAUDE.md` "QA debug surface" for the current shape.

## Suite invocations

### Android (default; debug APK installed on the running emulator)

```bash
python qa/srednabg_qa.py --suite smoke           # ~5 min — 1 zone + 1 sync + parser self-test
python qa/srednabg_qa.py --suite representative  # ~30 min — 6 hand-picked zones × 4 settings combos + sync set
python qa/srednabg_qa.py --suite scenarios       # ~20 min — edge cases (stop, dropout, off-ramp, U-turn, swap, auto-stop, dense-centerline, stop-silences-TTS, noisy-fix-rejected, parallel-motorway, mid-zone-join, …)
python qa/srednabg_qa.py --suite history         # ~7 min — History: records a traversal, retention=none records nothing, retention key round-trips (cross-platform)
python qa/srednabg_qa.py --suite sync            # ~5 min — zones happy + all-usable (served-data tripwire) + toggle-off + freshness + remote-older (recency gate) + offline; map disabled-gate
python qa/srednabg_qa.py --suite ui              # ~1 min — phone UI walk + font-scale cards + History "Show on map" gating
python qa/srednabg_qa.py --suite full-zones      # ~75 min @4× — all 74 zones, minimal asserts
python qa/srednabg_qa.py --suite nightly         # ~2 hr — representative + full-zones + scenarios + ui
```

#### Product flavors (`--flavor`)

The Android app ships two flavors differing only in the GPS provider (see
`android/CLAUDE.md` "Product flavors"): `aosp` (LocationManager — F-Droid +
GitHub) and `gms` (FusedLocationProvider — Play Store). The harness **does not
build or install** — install the flavor you want to test first (both share the
`com.demosten.srednabg` applicationId, so only one is installed at a time and
the harness tests whichever that is).

`--flavor {auto,aosp,gms}` (default `auto`) controls the `location.source_selected`
scenario that's prepended to the **smoke** and **representative** suites:

- `aosp` — asserts the app selects the LocationManager source (`SrednaBG.LocSrc:
  Selecting SystemLocationSource`). Fails if it sees `Fused…`, i.e. the FOSS
  build re-linked GMS or the wrong APK is installed.
- `gms` — asserts `FusedLocationSource` (on a **Google-APIs** emulator image;
  a plain AOSP image legitimately falls back to System).
- `auto` — only records which source was selected; doesn't pin the flavor.

**iOS skips this scenario entirely** (`_location_source_prefix()` in
`srednabg_qa.py` returns `[]` when the active device is iOS). iOS has a single
`CLLocationManager` path with no flavor/`LocationSource` factory, so it emits no
`SrednaBG.LocSrc` line and the tripwire could never pass there — the smoke /
representative suites run their remaining scenarios only.

```bash
# Install the aosp debug APK, then:
python qa/srednabg_qa.py --suite smoke --flavor aosp
# Install the gms debug APK, then:
python qa/srednabg_qa.py --suite smoke --flavor gms
```

Full flavor matrix (nightly-grade): build+install each flavor and run its
suite with the matching `--flavor`; the `/qa-app` skill orchestrates the
build+install+run loop since the harness itself doesn't build.

**Manual-only edge (not automated):** verifying the gms flavor's *fallback* —
`gms` APK on a device with **no** Play Services should select System — needs a
non-Google emulator image (plain AOSP, no GMS). The unit test
`LocationSourceSelectionTest` already covers the decision logic
(`chooseLocationSourceKind`) headlessly; the on-device fallback is a manual
check when a de-Googled image is available.

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
- **Several simulators booted at once**: `IosDevice` picks the booted simulator that actually has SrednaBG installed (`_booted_udid`), and `IosLogObserver` streams from that resolved UDID rather than the `booted` alias. Both matter — `simctl ... booted` is ambiguous with more than one runtime open (Simulator.app routinely keeps several), and before this the control channel and the log stream could address *different* devices, which showed up as every scenario timing out on a `DebugSync` line that had been logged elsewhere.
- **TTS muting**: there's no OS-level mute toggle on the simulator. The harness's `mute_audio()` POSTs `/mute?on=1` to the debug listener, which swaps the `AVSpeechTTSEngine` for a no-op while still emitting `speak:` log lines (so the parser self-test still trips on broken phrase changes).
- **Network offline**: `simctl status_bar` doesn't actually gate the network. `IosDevice.go_offline()` flips a `QAFlags.networkOffline` UserDefaults flag that makes the `DebugActionRouter` short-circuit sync requests to `Failed`. Observable behavior matches Android's airplane-mode path.
- **Mid-route GPS mutation**: the pump feeds the iOS debug listener's `/inject` endpoint (not `simctl location set`), which carries speed + bearing **and honors the pump's `time_ms` stamp** (forwarded into the injected `CLLocation`; injected fixes bypass the wall-clock age gate since they're fresh by delivery). Compressed plans therefore present the encoded cadence on iOS too — without the stamp, 4×-faster wall delivery used to infer 4× the encoded speed and clamp the display at 250 km/h. The compression-dependent edge scenarios (`gps_dropout`, `wrong_direction`, `u_turn`, `vehicle_swap`, `vehicle_type_limit_badge`) were written Android-first and are **now verified green on iOS** (full scenarios run, 2026-06).
- **`geo_fix` (`simctl location set`) does NOT re-deliver unchanged coordinates**: unlike `adb emu geo fix`, calling `simctl location set` repeatedly with the *same* lat/lng emits `didUpdateLocations` only once, then nothing (verified via os_log). A stationary hold must therefore **dither the coordinates** by a sub-metre each fix to keep CoreLocation delivering — which is also more realistic (a real receiver never freezes its coordinates). `speed_decay_after_stop` does exactly this (`STATIONARY_JITTER_DEG`, ~0.33 m → apparent ~2.4 km/h, well under its 10 km/h decay assertion) and runs green on both platforms. The one `geo_fix` scenario still **skipped on iOS** (`_ANDROID_ONLY_EDGE`) is `cold_start_spike`: it reproduces an Android `LocationTrackingService.kt` inference bug (`lastInferredSpeedKmh` reset) — iOS has its own `SpeedInference` units — and its cold-start seed has no `simctl` analog.

Reports land in `qa/reports/<suite>-<timestamp>/` (`junit.xml` + `summary.md` + `screenshots/`); exit code 0 = all passed. Invoke from a Claude Code session with the `/qa-app` skill — it runs the orchestrator, parses the report, and summarizes back in <200 words.

#### Xcode "Simulate Location" GPX (manual iOS testing)

Xcode's location simulation reads **only** `<wpt>` waypoints, not the harness's
`<trkpt>` track form, so hand-driving a zone on a device/Simulator needs converted
fixtures (committed under `qa/fixtures/gpx-xcode/`):

- `qa/fixtures/make_xcode_zone_route.py <zone-id>` — generates a sparse,
  smooth-heading, over-the-limit route with a short lead-in (so the
  Outside→In-zone entry announcement fires). Flags: `--speed-kmh`, `--spacing-m`,
  `--leadin-m`. Xcode plays sparse GPX at ~0.65–0.7× the encoded pace, so the
  default 240 km/h lands ~160 observed.
- `qa/fixtures/gpx_to_xcode.py <in.gpx> [out.gpx]` — converts an existing harness
  track-form GPX into Xcode `<wpt>` form.

## Definition of done

**Harness work is not complete until `ruff check qa/` reports "All checks
passed!"** (config at `qa/ruff.toml`), on top of actually running the suites the
change affects on a device.

The harness pins ruff's **default** rule set (`E4`, `E7`, `E9`, `F`) — real
defects: unused/misplaced imports, undefined names, dead locals. That is
deliberately narrower than `scrapers/ruff.toml`'s `E, F, I, B, UP`; the reason and
the migration path are recorded as LINT-Q01 in `test-data/known-lint-issues.md`
(gitignored). Anything else you choose not to fix belongs in that file too, with
the rule and the reason — a finding that is neither fixed nor registered is a
skipped lint, not an inherited one. See the repo-root `CLAUDE.md` "Definition of
done — linting".

## Adding scenarios

- YAML for "drive zone X at speed Y" variations.
- Python under `qa/scenarios/edge/` for mid-trip changes (dropout, U-turn, etc.) — register the module in `EDGE_SCENARIOS` in `qa/srednabg_qa.py`.
- Use `pump()` / `device.current().feed_point(...)` and `qa.settings` / `qa.sync` (not `qa.adb` directly) so the scenario runs on both platforms.
- User-reported bugs land with a reproducing scenario:
  - `stop_silences_tts.py` — Stop must silence in-flight TTS.
  - `dense_centerline.py` — short-segment zones don't false-exit/re-enter.
  - `tts_cold_start_leadin.py` — Android-only: a cold audio-focus session must prepend silent lead-in so the AA/Bluetooth route-open delay can't clip announcement starts.
  - `parallel_motorway.py` — driving the A3 past Кочериново must not open a phantom traversal of the I-1 zone beside it, replayed from the real OSM geometry in `qa/fixtures/a3_kocherinovo_corridor.yaml`. Carries an anti-vacuous guard that re-derives the *old* engine's entry gates and fails loudly if the geometry ever stops tripping them — the fixture was verified to FAIL against a temporarily-reverted engine and PASS against the fix, so it genuinely discriminates. It forbids `Unmeasured` as well as `InZone`, since the third zone state made the failure *softer* (quiet, no History row) but no less wrong on a road the car was never on.
  - `mid_zone_join.py` — start feeding fixes 5.8 km into `trakiya-01-east`, never crossing its entry camera, and assert the full `ZoneState.Unmeasured` contract end-to-end: the state is reached, no measured traversal ever opens, nothing is spoken, and `DUMP_HISTORY` reports no new row.
  - `sync/zones_all_usable.py` — a tripwire on the **served** data rather than the client. Forces a real re-fetch (requiring `Updated`) and fails on either line `ZoneSanitizer` emits, identically on both platforms: `zones repaired (n=…) ids=[…]` (a zone missing its truck/bus limit) or `zones dropped (n=…) ids=[…]` (placeholder `(0, 0)` endpoints, an empty centerline, no car limit). **The `repaired` half is the point of the scenario**: current builds handle that payload perfectly, and the 1.x clients the stores serve do not — iOS 1.x fails the whole `/api/zones` decode on it, so it is a silent fleet outage that looks like healthy data to QA. Three separate ways this scenario tried to pass vacuously, all now closed, all worth knowing before editing it: (1) the log lines arrive *before* the closing `DebugSync` event, so it must pass `collect=` to `sync.wait_for_sync` or the wait consumes them; (2) the recency gate returns `UpToDate` whenever the app bundles a fresher scrape than the cron has published (the normal state after `refresh-zones.sh`), so it backdates `cached_zone_version` and requires `Updated`; (3) it originally checked only `dropped`, which meant it stayed green on `i8-01-north` — the exact zone that broke every published install.
  - `jog_start_measured.py` — the positive-path companion to the above on `i3-02-north`, an ISSUE-001 zone whose centerline opens with a ~121 m backwards jog. A genuine approach there projects past 100 m of arc on its first matching fix, so it must still be **measured**: the run asserts `InZone` opens and `Unmeasured` never appears. Pairs with the core unit test `ZoneUnmeasuredTest."a zone whose centerline starts with a backwards jog is still measurable"`, which covers the same path at unit level.

## Manual zone feeding + full-zone direction validation (Android, debug build)

Three standalone adb tools (not part of `srednabg_qa.py`; they talk straight to
`DebugControlReceiver`) for exercising the zone state machine on the emulator:

- `qa/feed-zone.sh <idx|id|substring>` (helper: `feed_zone.py`) — drives a
  single zone for manual/visual inspection. It orients the route by the zone's
  **start/end endpoints** (`build_route` in `feed_zone.py`), i.e. the real
  carriageway direction, regardless of how the centerline points happen to be
  ordered. Run with no arg to list zones.
- `qa/validate-zones.sh` (helper: `validate_zones.py`) — drives **every** zone
  the same endpoint-oriented way and asserts, from the app's own
  `SrednaBG.TTS onZoneStateChanged` log, that (a) the **dominant** sustained
  traversal (≥75 % of in-zone fixes) is the **correct** zone id, (b) the intended
  zone isn't re-entered after exiting (flap), and (c) it exits cleanly. Exit 0 =
  all passed; `--quick` ≈ 2 km/zone; `--only 0,1,europa…` for a subset.

  It judges by the *dominant* traversal (not "any zone ever seen") on purpose:
  the feeder's 120 m lead-in can legitimately start inside the **adjacent**
  preceding zone, and a centerline that jogs at its very first vertex briefly
  reads as the opposite-direction **sibling** for a fix or two — both benign and
  timing-flaky. The genuine reversed-centerline bug instead spends the **whole**
  drive in the wrong zone (intended fraction ≈ 0), so it still fails hard
  (verified: `europa-01-north` on the un-aligned server data → "main traversal
  was europa-01-south, 0/343 in-zone fixes").

- `qa/colocated-zones.sh` (helper: `colocated_zones.py`) — drives a **continuous**
  route through a **co-located zone pair** (one camera ends zone A and begins
  zone B, so the engine steps `InZone(A) → Exiting(A) → InZone(B)` with **no
  Outside between the cameras**) and asserts, from the app's `SrednaBG.TTS` log,
  that **entering the second zone is announced**. 24 such pairs exist in the data
  (gap ≈ 0 m, mostly Trakiya; auto-detected by same road + direction +
  `end(A) ≈ start(B)`). Default drives the first detected pair; `--all` drives
  every pair; `--pair idA,idB` picks one; `--keep-online` uses the device's
  current data. Exit 0 = all passed.

  Regression for the `AudioAlertManager` `Exiting → InZone` fix (entry into B was
  silently dropped because the TTS layer only handled `Outside→InZone`). The
  assertion **correlates by order** — it requires a direct
  `prev=Exiting new=InZone zone=B` state line *immediately* followed by an entry
  speak — so a benign sibling-jog blip (which fires a spurious `Outside→InZone`)
  can't false-pass. `validate-zones.sh` can't catch this: it STOPs between zones,
  never producing the cross-zone transition.

Why this exists: the `scenarios/bulk/` suite drives the **centerline point order**
and only asserts "some zone was entered", so it **cannot** catch a zone stored
end-first (its `polylineBearing` points the wrong way → the app matches the
opposite-direction sibling and flaps; observed live: `europa-01-north` matched
`europa-01-south`). `validate-zones.sh` drives the true direction and checks the
entered **id**, so that data class fails loudly. Root cause was unaligned server
data; the scraper's `align_centerline_to_endpoints` aligns the bundle.

**The engine no longer depends on that alignment** (defense in depth): `ZoneDetector`
orients every centerline `start → end` at construction (`orientCenterlineToStart`),
so end-first data synced from a not-yet-redeployed `/api/zones` still detects
correctly. Because the device runs the *synced* data, not the bundle, use
`--keep-online` to test what a real device runs — it passes 72/72 even against the
reversed synced data. CI catch (no emulator): `ZoneDetectorTest` reversed-centerline
+ off-road-hysteresis cases.

Two device-state subtleties the harness handles, worth knowing for any zone
feeding:

- **Data under test**: the app syncs zones from `srednabg.com` into Room and
  that overrides the bundle. To validate the *bundled* (to-be-committed) data,
  `validate-zones.sh` forces the device **offline** + `pm clear` so the bundle
  loads; `--keep-online` tests the device's current data as-is.
- **Feed cadence / `time_ms`**: `DebugControlReceiver`'s `FEED_POINT` accepts an
  optional `time_ms` (epoch ms) extra. The GPS Kalman filter and speed inference
  key off `location.time` deltas, so injecting fixes a few ms apart in real time
  makes `dt→0`, the filter's process noise vanishes, and the smoothed dot lags
  off the road on bends → spurious off-road exits. `validate_zones.py` feeds as
  fast as adb allows but stamps each fix `--sim-dt-ms` (default 1000) apart, so
  the pipeline sees a realistic ~1 s cadence while the whole 74-zone sweep still
  finishes in minutes instead of hours. `feed-zone.sh` omits `time_ms` (real
  wall-clock), which is fine at its 1 s default `INTERVAL`.
- **Fix accuracy**: `FEED_POINT` also accepts an optional `accuracy` (meters)
  extra (default 5 m); `Device.feed_point(..., accuracy_m=)` threads it through.
  Used by the **Android-only** `scenarios/edge/noisy_fix_rejected.py` to feed a
  coarse fix and assert the service's `MAX_ACCURACY_M` (50 m) gate drops it
  (the defense-in-depth half of the GPS-only / no-NETWORK fix). It's listed in
  `_ANDROID_ONLY_EDGE` and skipped under `--platform ios` (iOS has no such gate;
  CoreLocation pre-filters).

## Map sync — feature-gated off

Both apps gate map sync behind `FeatureFlags.IS_MAP_SYNC_ENABLED` (Kotlin) / `FeatureFlags.isMapSyncEnabled` (Swift) until the production backend serves `/api/map/bundle.zip` + `map_hash`. While that's the case, `SYNC_MAP` returns `Skipped (feature disabled)` from both `DebugSyncReceiver` (Android) and `DebugActionRouter` (iOS).

`qa/scenarios/sync/map_disabled.py` triggers `SYNC_MAP` and asserts `outcome == Skipped` — this is the regression tripwire that catches accidental removal of either platform's gate. When the backend lights up and the flags flip, restore `qa/scenarios/sync/map_happy.py` (asserts `Updated`/`UpToDate` + on-disk integrity) and swap the entry in `SYNC_SCENARIOS` back. See `ios/CLAUDE.md` and `android/CLAUDE.md` for the gate-call-site map.

## Tripwire

When log line shapes change in either platform's app — `AudioAlertManager.kt` / `LocationTrackingService.kt` on Android, `QALog` + `ZoneTrackingService.swift` / `CLLocationTracker.swift` / `AudioAlertManager.swift` on iOS — the smoke suite's parser self-test (`qa/scenarios/parser_self_test.py`, always the smoke suite's last scenario) fails loudly, naming the missing event type + the dead regex and quoting the unparsed lines. It works off `LogObserver.type_counts` / `unparsed_samples`, which accumulate across the whole suite (`clear()` deliberately keeps them). Fix the regex in `qa/parsers.py` (the shared module) and both platforms re-converge. Note it judges the *whole smoke run* — invoking it alone via `--filter parsers` fails vacuously.

## Store-screenshot tooling

Two orchestrators live alongside the QA harness — they share `qa/screenshots/loader.py` + `qa/screenshots/shots.yaml` but are otherwise independent of the suites above:

- `qa/srednabg_screenshots.py` — drives the running emulator / Simulator to capture the raw store PNGs. Skill: `/screenshot-app`.
- `qa/srednabg_frame_screenshots.py` — **offline** post-processor that composes Waze-style marketing frames (solid bg + centered title + smaller phone screenshot with rounded corners + thin black border) from the raw PNGs. Skill: `/frame-screenshots`. No emulator / Simulator involved.

### Outputs (tracked in git)

Both write under `web/screenshots/`, which is committed so the F-Droid staging script can stage the framed shots and the store listing stays reproducible:

- Raw: `web/screenshots/<platform>/NN-<platform>-<theme>-<lang>.png`
- Framed: `web/screenshots/<platform>/framed/NN-<theme>-<lang>.png`

Regenerate via the skills and commit the result. `web/CLAUDE.md` explains how the marketing site picks up the framed PNGs at deploy time.

### `qa/screenshots/shots.yaml`

Single source of truth for both scripts. Top-level keys:

- `zone_id`, `languages`, `shots:` — consumed by capture.
- `frame:` block + per-shot `background` / `title` — consumed only by framing. Capture ignores them. The renderer auto-shrinks oversized titles and supports a hard `\n` in title text; literal `#RRGGBB` works anywhere a palette key (from `frame.colors`) is accepted.
- `frame.chrome_mask.<platform>` — paints a solid band over the top of each raw screenshot before rounded-corner cropping, to hide the OS status bar. Color is sampled at render time from the bottom tab bar (uniform per theme). `top_px: 0` disables the mask for that platform.

### Python dependencies

`qa/requirements.txt` (PyYAML + Pillow ≥10). The QA harness itself is stdlib + PyYAML; Pillow is only needed for `/frame-screenshots`. These install into the single root `.venv` via `bash scripts/setup-python.sh` (per project preference: pip + `requirements.txt`, never `pyproject.toml`). The `qa/*.sh` wrappers preflight that venv (`setup-python.sh --check`) and run through `.venv/bin/python`, so they work without activating it; the `python qa/*.py` entry points auto-use the venv if present, else print the same "run `bash scripts/setup-python.sh`" instruction instead of a `ModuleNotFoundError`.

### Bundled font

`qa/screenshots/fonts/Nunito-Bold.ttf` ships with the repo (SIL OFL 1.1; license at `qa/screenshots/fonts/LICENSE-OFL.txt`) so framing works without a system-font hunt and Cyrillic renders correctly. Don't replace it with a non-OFL font.
