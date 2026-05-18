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
| `scenarios` | ~20 min | 10 edge cases (stop, dropout, off-ramp, U-turn, swap, auto-stop, etc.) |
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

## Sibling tooling

`qa/srednabg_screenshots.py` (skill: `/screenshot-app`) drives the running
emulator / Simulator to capture raw store PNGs. `qa/srednabg_frame_screenshots.py`
(skill: `/frame-screenshots`) is an offline post-processor that composes
Waze-style marketing frames from those raw PNGs. Both share
`qa/screenshots/shots.yaml` but are independent of the suites above. See
`qa/CLAUDE.md` "Store-screenshot tooling" for the workflow.

## Skill entry

Invoke from a Claude Code session via `/qa-app` — it runs the orchestrator,
parses the report, and summarizes results back to you in <200 words.
