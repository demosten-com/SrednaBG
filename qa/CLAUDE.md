# qa/

End-to-end QA harness (Python, stdlib + PyYAML). Drives the running phone emulator via `adb emu geo fix`, parses typed events from filtered `adb logcat`, asserts on the full app stack (zone state machine, audio alerts, settings, sync, UI). Pairs with the JVM unit tests — units cover algorithm math, this covers everything they don't.

## Architecture

- `qa/srednabg_qa.py` — entry point / orchestrator
- `qa/adb.py` — shells out to `adb`
- `qa/logcat.py` — tails one filtered logcat subprocess, parses lines into typed events
- `qa/events.py` — typed event dataclasses
- `qa/drive.py` — parses GPX into a `DrivePlan`, pumps `adb emu geo fix` at the right cadence
- `qa/assertions.py` — `expect` / `expect_in_order` / `expect_never` over the event queue
- `qa/runner.py` — runs ordered scenario steps with per-scenario log-buffer isolation
- `qa/settings.py` — flips settings via `DebugControlReceiver` (no DataStore proto write race)
- `qa/sync.py` — triggers `DebugSyncReceiver` and inspects on-disk map bundle integrity
- `qa/ui.py`, `qa/report.py` — UI walk + report generation
- Scenarios under `qa/scenarios/{bulk,representative,edge,sync,ui}/`
- Fixtures in `qa/fixtures/` (`tts_phrases.yaml`, GPX)

Depends on `android/`'s debug-only `DebugSyncReceiver` and `DebugControlReceiver` (see `android/CLAUDE.md`).

## Suite invocations (debug APK installed on the running phone emulator)

```bash
python qa/srednabg_qa.py --suite smoke           # ~5 min — 1 zone + 1 sync + parser self-test
python qa/srednabg_qa.py --suite representative  # ~30 min — 6 hand-picked zones × 4 settings combos + sync set
python qa/srednabg_qa.py --suite scenarios       # ~20 min — 7 edge cases (stop, dropout, off-ramp, U-turn, swap, …)
python qa/srednabg_qa.py --suite sync            # ~5 min — zones happy + offline; map happy + integrity
python qa/srednabg_qa.py --suite ui              # <1 min — phone UI walk
python qa/srednabg_qa.py --suite full-zones      # ~75 min @4× — all 72 zones, minimal asserts
python qa/srednabg_qa.py --suite nightly         # ~2 hr — representative + full-zones + scenarios + ui

# One-time regens
python -m qa.scenarios.bulk._generate            # regenerate per-zone YAMLs after zones.json change
python -m qa.fixtures._extract_tts > qa/fixtures/tts_phrases.yaml  # refresh TTS fixture
```

Reports land in `qa/reports/<suite>-<timestamp>/` (`junit.xml` + `summary.md` + `screenshots/`); exit code 0 = all passed. Invoke from a Claude Code session with the `/qa-app` skill — it runs the orchestrator, parses the report, and summarizes back in <200 words.

## Adding scenarios

- YAML for "drive zone X at speed Y" variations.
- Python under `qa/scenarios/edge/` for mid-trip changes (dropout, U-turn, etc.) — register the module in `EDGE_SCENARIOS` in `qa/srednabg_qa.py`.

## Tripwire

When `AudioAlertManager.kt` phrases or `LocationTrackingService.kt` log formats change, the smoke suite's parser self-test fails loudly with a pointer to the affected line — fix the regex in `qa/logcat.py`.
