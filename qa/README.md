# SrednaBG QA harness

End-to-end test layer that drives a running Android emulator (via `adb emu
geo fix`) or a booted iOS Simulator (via `xcrun simctl` + the app's loopback
debug listener), observes typed events parsed from the platform log stream,
and asserts on the full app stack: zone state machine, audio alerts,
settings, sync, UI.

Pairs with the existing JVM / Swift unit tests (`cd android && ./gradlew
:core:test :app:test`; `cd ios && swift test`) — the unit tests cover
algorithm math, this harness covers everything they don't.

See `qa/CLAUDE.md` for the platform-by-platform invocation matrix and
caveats; this README sticks to the Android quick-start.

## Quick start

```bash
# 1. boot phone emulator + ensure debug APK is installed
(cd android && ./gradlew :app:assembleDebug)
adb install -r android/app/build/outputs/apk/debug/app-debug.apk

# 2. pre-grant runtime permissions (the harness does this too on each run)
adb shell pm grant com.demosten.srednabg android.permission.ACCESS_FINE_LOCATION
adb shell pm grant com.demosten.srednabg android.permission.POST_NOTIFICATIONS

# 3. run a suite
python qa/srednabg_qa.py --suite smoke

# (one-time) generate per-zone YAMLs for the full bulk pass
python -m qa.scenarios.bulk._generate

# (one-time) extract TTS phrases into a fixture for substring assertions
python -m qa.fixtures._extract_tts > qa/fixtures/tts_phrases.yaml
```

## Suites

| Suite | Time | Coverage |
|-------|------|----------|
| `smoke` | ~5 min | 1 zone, 1 settings combo, 1 sync, parser self-test |
| `representative` | ~30 min | 6 hand-picked zones × 4 settings combos + sync set |
| `full-zones` | ~75 min @ 4× | All 72 zones × constant-speed pass × 4 minimal asserts |
| `scenarios` | ~20 min | 12 edge cases (stop, dropout, off-ramp, U-turn, swap, auto-stop, dense-centerline, stop-silences-TTS, etc.) |
| `sync` | ~5 min | Zones happy + offline; map happy + integrity |
| `ui` | <1 min | Phone UI walk via mobile-mcp / adb input |
| `nightly` | ~2 hr | representative + full-zones + scenarios + ui |

Reports land in `qa/reports/<suite>-<timestamp>/` (junit.xml + summary.md +
screenshots/).

## Architecture in 1 paragraph

`qa/device.py` is the platform facade — `AndroidDevice` (delegates to
`qa/adb.py`) or `IosDevice` (wraps `xcrun simctl` + HTTP POSTs to the app's
debug listener); everything else talks through `device.current()`.
`qa/log_observer.py` + the per-platform observers in `qa/devices/` tail one
filtered log stream and parse each line into typed events from `qa/events.py`
using the shared regex set in `qa/parsers.py`. `qa/drive.py` parses GPX into
a `DrivePlan` (list of `(lat, lng, t_offset_ms)`) and pumps `device.geo_fix()`
at the right cadence. `qa/assertions.py` provides `expect`, `expect_in_order`,
`expect_never` over the event queue. `qa/runner.py` runs ordered scenario
steps with per-scenario log-buffer isolation. `qa/settings.py` flips app
settings via the active device (Android: `DebugControlReceiver` broadcast;
iOS: HTTP POST to the debug listener). `qa/sync.py` triggers a sync and
inspects on-disk map bundle integrity. `qa/logcat.py` survives as a
compatibility shim re-exporting `LogObserver as LogcatObserver` — new code
imports from `qa.log_observer` + `qa.parsers`.

## Adding a scenario

YAML for variations of "drive zone X at speed Y":

```yaml
# qa/scenarios/representative/my_scenario.yaml
zone_id: trakiya-01-east
speed_kmh: 110
compression: 4.0
expect_enter: true
expect_exit: true
settings: S2
```

Python for anything more complex (mid-trip changes, GPS dropout, U-turn, etc):

```python
# qa/scenarios/edge/my_thing.py
from ._helpers import base_plan, scenario_setup, scenario_teardown
from ...runner import Scenario, step_lambda
from ...drive import pump

def build() -> Scenario:
    plan = base_plan("trakiya-01-east", speed_kmh=110).compressed(2.0)
    return Scenario(
        name="edge.my_thing",
        steps=[
            step_lambda("setup", scenario_setup),
            step_lambda("drive", lambda ctx: pump(plan)),
            # asserts...
        ],
        teardown=scenario_teardown,
    )
```

Then add the module name to `EDGE_SCENARIOS` in `qa/srednabg_qa.py`.

User-reported bugs should land with a qa/ scenario that reproduces them
(`stop_silences_tts.py`, `dense_centerline.py` are recent examples).

## Standalone zone-feeding tools (Android, debug build)

Separate from `srednabg_qa.py` — they drive `DebugControlReceiver` directly.
See `qa/CLAUDE.md` for the offline/`time_ms` cadence details.

| Tool | Purpose |
|------|---------|
| `qa/feed-zone.sh <idx\|id\|substring>` | Drive one zone (endpoint-oriented) for visual inspection; no arg lists zones. |
| `qa/validate-zones.sh` | Drive **every** zone and assert the correct id is detected with no flapping. `--quick`, `--only`, `--keep-online`. |
| `qa/colocated-zones.sh` | Drive a co-located zone pair (back-to-back camera) and assert the second zone's entry is announced. `--all`, `--pair`, `--keep-online`. |

## Xcode "Simulate Location" GPX (iOS manual testing)

For driving a zone by hand on an iOS device/Simulator (Xcode reads only
`<wpt>` waypoints, not the harness's `<trkpt>` track form):

- `qa/fixtures/make_xcode_zone_route.py <zone-id>` — generate a sparse,
  smooth-heading over-the-limit route with a short lead-in (so the
  Outside→In-zone entry announcement fires). Outputs to `fixtures/gpx-xcode/`.
- `qa/fixtures/gpx_to_xcode.py <in.gpx>` — convert an existing harness
  track-form GPX into Xcode `<wpt>` form.

## Updating after app changes

When `AudioAlertManager.kt` (or the iOS `AudioAlertManager.swift`) phrases
change, regenerate `tts_phrases.yaml`. When zones.json changes, re-run
`python -m qa.scenarios.bulk._generate` and commit the diff. When the log
format changes — Kotlin `LocationTrackingService.kt` / `AudioAlertManager.kt`
on Android, `QALog` + `ZoneTrackingService.swift` / `CLLocationTracker.swift`
/ `AudioAlertManager.swift` on iOS — the smoke suite's parser self-test
fails loudly with a pointer to the affected line. Fix the regex in
`qa/parsers.py` (the shared module) and both platforms re-converge.

## Known acceptable gaps

- `adb emu geo fix` ignores velocity on most builds → FLP synthesizes from
  successive positions (matches what the Kalman filter expects). Fine.
- Periodic TTS uses wall-clock 30s; at 4× compression there are fewer
  periodic announcements per zone. Bulk asserts are agnostic to exact count.
- iOS Simulator's `simctl location set` is ≈100–500 ms per point vs. <10 ms
  for `adb emu geo fix`, so edge-case scenarios that fan fixes rapidly
  (`gps_dropout`, `wrong_direction`, `u_turn`, `vehicle_swap`) are
  Android-only until a faster iOS pump lands.
- AAOS support is a planned tier (different LocationManager source path +
  Surface rendering).

## Store screenshots (Android + iOS)

Two-step pipeline that shares `qa/screenshots/shots.yaml` but is otherwise
independent of the QA suites above:

1. **Capture** raw PNGs from a running emulator / Simulator
   → `qa/srednabg_screenshots.py` (skill: `/screenshot-app`)
2. **Frame** them offline into Waze-style marketing PNGs
   → `qa/srednabg_frame_screenshots.py` (skill: `/frame-screenshots`)

Outputs (both trees are tracked in git):

- Raw:    `web/screenshots/<platform>/NN-<platform>-<theme>-<lang>.png`
- Framed: `web/screenshots/<platform>/framed/NN-<theme>-<lang>.png`

### Prerequisites

| Platform | What must be running before capture |
|----------|-------------------------------------|
| Android  | Booted emulator with the **debug** APK installed (`adb install -r android/app/build/outputs/apk/debug/app-debug.apk`). |
| iOS      | macOS host, booted Simulator with the **Debug** build installed (`xcrun simctl install booted <path>.app`). Debug-only — the loopback HTTP debug listener + `QALog` are `#if DEBUG`. Simulator needs an active GUI session (Metal); no headless. |

Framing additionally needs Pillow: `pip install -r qa/requirements.txt`.

### Capture — `qa/srednabg_screenshots.py`

```
python qa/srednabg_screenshots.py <android|ios> [shot] [lang] [--theme T] [--allow-adb-fallback]
```

| Arg / flag | Values | Default | Meaning |
|------------|--------|---------|---------|
| `platform` (positional, required) | `android`, `ios` | — | Which backend to drive. |
| `shot` (positional, optional) | NN (e.g. `3`) or name slug (e.g. `map-north-green`) | all shots | Run a single shot from `shots.yaml`. |
| `lang` (positional, optional) | `en`, `bg` | both | Single language. May also be passed as `--lang` when you want all shots in one language without naming a shot. |
| `--theme` | `light`, `dark` | `light` | Forces the device theme **and** is embedded in the output filename so light/dark PNGs coexist. |
| `--allow-adb-fallback` | flag | off | Android-only, headless mode: tap the bottom-nav by coordinate when no Claude session is acking `tap_tab` cues. Off by default — the skill normally drives taps via mobile-mcp. |

Shot names currently in `shots.yaml`: `home-outside-90`,
`home-in-zone-green`, `home-in-zone-yellow`, `map-north-green`,
`map-heading-yellow-dark`, `map-heading-yellow-light`,
`map-heading-red-light`, `settings-top`.

#### Common capture invocations

```bash
# Full set, light theme, both languages — Android
python qa/srednabg_screenshots.py android

# Full set, dark theme, both languages — iOS
python qa/srednabg_screenshots.py ios --theme dark

# All shots, BG only — Android, dark
python qa/srednabg_screenshots.py android --theme dark --lang bg

# A single shot by index, both languages — iOS
python qa/srednabg_screenshots.py ios 4

# A single shot by name + single language — Android
python qa/srednabg_screenshots.py android map-north-green en

# Both themes (run twice — theme is part of the filename, no overwrite)
python qa/srednabg_screenshots.py android --theme light
python qa/srednabg_screenshots.py android --theme dark
```

> To produce the **full marketing set** (both platforms × both themes ×
> both languages), run the four `<platform> --theme <theme>` combinations.

### Frame — `qa/srednabg_frame_screenshots.py`

Operates only on PNGs already in `web/screenshots/<platform>/`. No
emulator / Simulator involved.

```
python qa/srednabg_frame_screenshots.py <android|ios> [shot] [lang] [--theme T] [--force]
```

| Arg / flag | Values | Default | Meaning |
|------------|--------|---------|---------|
| `platform` (positional, required) | `android`, `ios` | — | Which raw tree to read from. |
| `shot` (positional, optional) | NN or name slug | all | Render a single shot. |
| `lang` (positional, optional) | `en`, `bg` | both | Single language. |
| `--theme` | `light`, `dark` | `light` | Selects which raw PNG variant to frame (must match the `--theme` you captured under). |
| `--force` | flag | off | Re-render even when the framed PNG is newer than the raw input. |

#### Common framing invocations

```bash
# Frame everything captured for Android, light theme
python qa/srednabg_frame_screenshots.py android

# Frame iOS dark-theme set in both languages
python qa/srednabg_frame_screenshots.py ios --theme dark

# Re-render a single Android shot in EN (e.g. after tweaking title text)
python qa/srednabg_frame_screenshots.py android 2 en --force

# Re-render one shot across both languages and themes (two runs)
python qa/srednabg_frame_screenshots.py android home-in-zone-green --theme light --force
python qa/srednabg_frame_screenshots.py android home-in-zone-green --theme dark  --force
```

Iterating on a title or background color only requires re-running the
framer — capture stays untouched. See `qa/CLAUDE.md` "Store-screenshot
tooling" for the `shots.yaml` schema (`frame:` block, per-shot
`background` / `title`, `chrome_mask`).

## Skill entry

Invoke from a Claude Code session via:

- `/qa-app` — runs the orchestrator, parses the report, summarizes in <200 words.
- `/screenshot-app` — captures raw store PNGs (wraps `srednabg_screenshots.py`).
- `/frame-screenshots` — composes framed marketing PNGs (wraps `srednabg_frame_screenshots.py`).
