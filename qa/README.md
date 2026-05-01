# SrednaBG QA harness

End-to-end test layer that drives the running emulator via `adb emu geo fix`,
observes typed events parsed from `adb logcat`, and asserts on the full app
stack: zone state machine, audio alerts, settings, sync, UI.

Pairs with the existing JVM unit tests (`cd android && ./gradlew :core:test
:app:test`) — the unit tests cover algorithm math, this harness covers
everything they don't.

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
| `scenarios` | ~20 min | 7 edge cases (stop, dropout, off-ramp, U-turn, swap, etc.) |
| `sync` | ~5 min | Zones happy + offline; map happy + integrity |
| `ui` | <1 min | Phone UI walk via mobile-mcp / adb input |
| `nightly` | ~2 hr | representative + full-zones + scenarios + ui |

Reports land in `qa/reports/<suite>-<timestamp>/` (junit.xml + summary.md +
screenshots/).

## Architecture in 1 paragraph

`qa/adb.py` shells out to `adb`. `qa/logcat.py` tails one filtered logcat
subprocess and parses each line into typed events from `qa/events.py`.
`qa/drive.py` parses GPX into a `DrivePlan` (list of `(lat, lng, t_offset_ms)`)
and pumps `adb emu geo fix` at the right cadence. `qa/assertions.py` provides
`expect`, `expect_in_order`, `expect_never` over the event queue.
`qa/runner.py` runs ordered scenario steps with per-scenario log-buffer
isolation. `qa/settings.py` flips app settings via the debug
`DebugControlReceiver` broadcast (no DataStore proto write race).
`qa/sync.py` triggers `DebugSyncReceiver` and inspects on-disk map bundle
integrity.

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

When `AudioAlertManager.kt` phrases change, regenerate `tts_phrases.yaml`.
When zones.json changes, re-run `python -m qa.scenarios.bulk._generate` and
commit the diff. When the Kotlin log format at `LocationTrackingService.kt`
or `AudioAlertManager.kt` changes, the smoke suite's parser self-test
fails loudly with a pointer to the affected line — fix the regex in
`qa/logcat.py`.

## Known acceptable gaps

- `adb emu geo fix` ignores velocity on most builds → FLP synthesizes from
  successive positions (matches what the Kalman filter expects). Fine.
- Periodic TTS uses wall-clock 30s; at 4× compression there are fewer
  periodic announcements per zone. Bulk asserts are agnostic to exact count.
- Phone emulator only by default. AAOS support is a planned tier (different
  LocationManager source path + Surface rendering).

## Skill entry

Invoke from a Claude Code session via `/qa-app` — it runs the orchestrator,
parses the report, and summarizes results back to you in <200 words.
