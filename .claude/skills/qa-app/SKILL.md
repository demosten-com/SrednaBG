---
name: qa-app
description: Run the SrednaBG end-to-end QA harness against the running phone emulator and summarize the result. Use when the user says "run QA", "/qa-app", "test the app", "check the build", or asks to drive any of the suites (smoke, representative, full-zones, scenarios, sync, ui, nightly). Also use when the user asks to extend or update the harness for a new app version.
---

# qa-app — SrednaBG end-to-end QA harness

You are running an automated QA orchestrator that drives a real Android phone emulator. The harness lives at `qa/` in the project root. Your job: invoke the right suite, monitor the run, and report results concisely.

## Inputs you accept

- `smoke` (default if no arg) — ~5 min, 1 zone + 1 sync
- `representative` — ~30 min, 6 zones × 4 settings + sync set
- `full-zones` — ~75 min @ 4× compression, all 72 zones
- `scenarios` — ~20 min, 7 edge cases (stop, dropout, off-ramp, U-turn, swap, recovery, wrong-direction)
- `sync` — ~5 min, zones happy/offline + map happy
- `ui` — <1 min, phone UI walk
- `nightly` — ~2 hr, the whole thing

If the user didn't specify, default to `smoke` and tell them which suites are available.

## Pre-flight checks (always run first)

1. `adb devices` — must show exactly one device. If none, tell the user to boot the emulator.
2. **Mute the emulator** — always, before any suite (TTS alerts are loud). Run:
   ```bash
   adb shell input keyevent 164
   adb shell "cmd media_session volume --stream 3 --set 0"
   adb shell "cmd media_session volume --stream 1 --set 0"
   adb shell "cmd media_session volume --stream 5 --set 0"
   ```
3. `adb shell pm list packages com.demosten.srednabg` — package must be installed. If missing, build + install:
   ```bash
   (cd android && ./gradlew :app:assembleDebug)
   adb install -r android/app/build/outputs/apk/debug/app-debug.apk
   ```
4. Confirm the existing unit tests pass (skip if user explicitly says "just integration"):
   ```bash
   (cd android && ./gradlew :core:test :app:test)
   ```
5. For `full-zones`: ensure bulk YAMLs exist (`ls qa/scenarios/bulk/*.yaml | wc -l` should be 72). If not:
   ```bash
   python -m qa.scenarios.bulk._generate
   ```
6. For TTS-asserting scenarios: ensure `qa/fixtures/tts_phrases.yaml` exists. If not:
   ```bash
   python -m qa.fixtures._extract_tts > qa/fixtures/tts_phrases.yaml
   ```

## Running

```bash
python qa/srednabg_qa.py --suite <name>
```

The orchestrator streams scenario results live (one line per scenario: PASS/FAIL + duration). For long runs (`full-zones`, `nightly`), use `run_in_background: true` and check back periodically.

## After it finishes

1. Read the summary at `qa/reports/<suite>-<timestamp>/summary.md` (path printed at the end of stdout).
2. Report to the user:
   - One-line headline: "X/Y passed in Zm" plus PASS/FAIL.
   - If anything failed: list the failed scenario names with a one-line failure-message head each. Don't dump the whole log buffer — link the report path instead.
   - If everything passed: brief mention of what was covered.
3. Keep your summary under 200 words. The user can drill into the report for detail.

## Failure triage

When a scenario fails, read in this order before claiming a root cause:
- `qa/reports/<suite>-<ts>/summary.md` — failure section has the assertion message + last 30 log lines
- `qa/reports/<suite>-<ts>/screenshots/` — only present for `ui` suite
- `adb logcat -b crash -d` — separately captures any FATAL EXCEPTION
- The Kotlin source the assertion references (e.g. `AudioAlertManager.kt:200` for TTS log format)

Common failure modes:
- "log format changed at AudioAlertManager.kt:NNN" — Kotlin source changed the log line format. Update regex in `qa/logcat.py`.
- "timed out waiting for ZoneStateChange" — GPS pump probably isn't reaching the app. Check `adb shell pidof com.demosten.srednabg` and that "Start tracking" succeeded (`adb logcat -s SrednaBG.Loc:V -d | grep onStartCommand`).
- "crash buffer non-empty" — read `adb logcat -b crash -d`. App-side bug, not a harness bug.
- "no DebugSync result for SYNC_X" — debug receivers aren't registered. Confirm `adb shell dumpsys package com.demosten.srednabg | grep DebugControl` shows the receiver.

## Updating the harness for a new app version

When asked to update tests for a new model/version:
1. Run smoke first. Failures point at concrete drift.
2. Brittle surface concentrated in three files:
   - `qa/logcat.py` — regexes anchored to Kotlin log line format
   - `qa/adb.py` — package + activity + receiver class names
   - `qa/fixtures/tts_phrases.yaml` — TTS substring expectations (regenerate via `python -m qa.fixtures._extract_tts`)
3. Scenario logic in `qa/scenarios/**` rarely changes — those are mostly data.
4. After fixing, re-run smoke until green, then re-run representative.

## Files you should know

- Entry: `qa/srednabg_qa.py`
- Suites dict: `SUITE_BUILDERS` in the entry file
- Scenarios: `qa/scenarios/{bulk,representative,edge,sync,ui}/`
- Debug-only Kotlin (added by this harness): `android/app/src/debug/kotlin/bg/srednabg/app/debug/DebugControlReceiver.kt`
- Existing Kotlin entry points the harness depends on:
  - `LocationTrackingService.kt` (TAG `SrednaBG.Loc`)
  - `AudioAlertManager.kt` (TAG `SrednaBG.TTS`, phrase strings at lines 149–186)
  - `DebugSyncReceiver.kt` (TAG `DebugSync`)

## Always do

- Confirm exactly one emulator is attached before running.
- Default to `smoke` when ambiguous.
- Quote the report path so the user can `cat qa/reports/<...>/summary.md` for details.
- Keep summaries under 200 words.

## Never do

- Don't re-run a failed suite without reading the failure first.
- Don't modify scenario assertions to make a failing scenario pass without first checking the app behavior is actually correct.
- Don't run `nightly` without confirming with the user — it's 2 hours.
