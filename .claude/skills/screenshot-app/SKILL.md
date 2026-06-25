---
name: screenshot-app
description: Capture SrednaBG App Store / Play Store screenshots. Use when the user says "/screenshot-app", "store screenshots", "app store screenshots", "play store screenshots", or asks to (re)capture any of the six store shots on the phone emulator (Android) or iOS Simulator. The shot list lives in qa/screenshots/shots.yaml — read it if the user asks what's captured or wants to add/edit shots.
---

# screenshot-app — App Store / Play Store screenshot harness

You are driving an automated screenshot harness that captures the six store screenshots for SrednaBG on either Android (emulator) or iOS (Simulator), in both Bulgarian and English. The shot list is declarative — `qa/screenshots/shots.yaml`. The orchestrator is `qa/srednabg_screenshots.py`.

Your job: ask which platform if missing, run pre-flight, launch the orchestrator, drive the bottom-tab taps via mobile-mcp when the orchestrator asks for them, report the produced PNGs.

## Inputs you accept

The user invokes you as `/screenshot-app <android|ios> [shot] [lang] [--theme light|dark]`:

- `android` / `ios` — required. Tells the harness which build to drive.
- `shot` — optional. Either an `NN` (1-6) or a `name` (e.g. `map-north-green`).
- `lang` — optional `en` / `bg`. Both run when omitted. Also accepted as `--lang en|bg`.
- `--theme light|dark` — optional. Forces the system/device appearance before
  capture and gets embedded in the output filename. Default `light` when
  omitted. (Per-shot in-app *map* theme stays defined in `shots.yaml` —
  `--theme` is the OS-wide appearance.)

If the user typed just `/screenshot-app` (no platform), **ask** which platform — there's no safe default.

## Pre-flight (always)

Run these in order. Skip step 4 if the user explicitly asked for "fast" / "no build".

1. **Device check**
   - Android: `adb devices` must show exactly one device.
   - iOS: `xcrun simctl list devices booted` must show exactly one booted simulator.
   - If neither is present, tell the user how to boot one and stop.
2. **Mute** (per the `Mute emulator before QA` memory — TTS is loud and would play during the run).
   - Android: `adb shell input keyevent 164` then `adb shell "cmd media_session volume --stream 3 --set 0"` (etc., same as qa-app skill).
   - iOS: the orchestrator handles this via the in-app `/mute` debug endpoint during `preflight()`.
3. **Package installed?**
   - Android: `adb shell pm list packages com.demosten.srednabg`.
   - iOS: `xcrun simctl get_app_container booted com.demosten.srednabg` (exit 0 = installed).
4. **Build + install if missing or stale**.
   - Android:
     ```bash
     (cd android && ./gradlew :app:assembleDebug)
     adb install -r android/app/build/outputs/apk/debug/app-debug.apk
     ```
   - iOS:
     ```bash
     (cd ios && xcodebuild -scheme SrednaBG -destination 'platform=iOS Simulator,name=<name-from-simctl-list>' -configuration Debug build)
     # then locate the .app and `xcrun simctl install booted <path>`
     ```
     If unsure of the destination, ask the user once.

## Running the orchestrator

Ensure the Python env first (single root `.venv`), then spawn the harness in the **background** so you can drive cues while it runs:

```bash
bash scripts/setup-python.sh --check || bash scripts/setup-python.sh
.venv/bin/python qa/srednabg_screenshots.py <platform> [shot] [lang] [--theme light|dark]
```

`--theme` defaults to `light`; pass it through verbatim from the user's invocation. The theme value lands in both the system appearance (via `simctl ui ... appearance` / `cmd uimode night`) and the output filename.

The first stdout line prints the **signal directory** (e.g. `signal dir: qa/reports/screenshots-android-YYYYMMDD-HHMMSS/signal`). Remember it — you'll watch this directory for cue files.

### The cue-ack loop

The orchestrator pauses on every tab switch by writing `cue-NNNN.json` into the signal directory. While the orchestrator is running, you watch that directory and respond to every new cue. For each cue:

1. Read the file. It looks like:
   ```json
   {"seq": 7, "kind": "tap_tab", "tab": "map", "accessibility_id": "tab-map", "ts": "..."}
   ```
2. If `kind == "tap_tab"`:
   - Call `mcp__mobile-mcp__mobile_list_elements_on_screen` and find the element whose accessibility id / resource-id matches `accessibility_id` (e.g. `tab-map`).
   - Call `mcp__mobile-mcp__mobile_click_on_screen_at_coordinates` at the element's centre.
3. Write the matching ack file: `signal/ack-NNNN.json` with content `{"by": "skill", "ok": true}`. The orchestrator polls every 200 ms — write the file as soon as the tap completes.

The orchestrator's default ack timeout is 8 s per tab switch. If you miss the window, the orchestrator on Android can fall back to coordinate-tap (only when `--allow-adb-fallback` is passed) and continue; iOS will hard-fail.

If you have to pick coordinates yourself (no accessibility id surfaced — sometimes happens on the first frame after locale change), look at the bottom-nav bar and tap centre-of-tab. Sizes:
- Pixel 8a portrait 1080×2400 — tabs at y≈2253, x∈{180, 540, 900}.
- iPhone 15 portrait 1179×2556 — tab bar near y≈2470, x∈{200, 590, 980}.

### Headless smoke

When the user wants to test the orchestrator alone (no UI driver), pass `--allow-adb-fallback`. The orchestrator will tap via coordinates after timing out on each cue. Android only.

## After it finishes

The orchestrator prints `produced N screenshot(s):` followed by paths under `web/screenshots/<platform>/`. Report concisely:

- One-line headline: "N PNGs in web/screenshots/<platform>/, Xm Ys."
- List the file names (not full paths) for spot-checking.
- If any cues timed out or the orchestrator raised, surface the error and point at the signal dir for debugging.

Keep your final summary under 200 words.

## Failure triage

- **Cues pile up unacked**: the mobile-mcp call failed silently or the element wasn't surfaced. Check `mcp__mobile-mcp__mobile_list_elements_on_screen` output — on Android the tab `resource-id`s appear because the app sets `Modifier.semantics { testTagsAsResourceId = true }` on the parent NavigationBar. If they're missing, the debug build is stale; rebuild.
- **Wrong band (green where yellow expected, etc.)**: open the produced PNG, then look at the stdout for which shot drove which sequence. Bump the band tail duration in `qa/screenshots/sequencer.py` (`drive_band_tail`) — yellow needs a brief prefix at high speed, red needs sustained high speed.
- **Status bar still has user notifications / a phone-call clock**:
  - Android: `adb shell settings put global sysui_demo_allowed 1` may have failed (`WRITE_SECURE_SETTINGS`). Emulator-only feature; tell the user.
  - iOS: another `simctl status_bar` override is fighting. `xcrun simctl status_bar booted clear` then re-run.
- **Locale didn't switch on Android**: `setApplicationLocales` recreates `MainActivity`, which sometimes restores the previous tab. The orchestrator inserts a 2 s wait after the language flip, but if the recreated UI is showing the wrong tab, the next cue you receive will be `tap_tab` for the correct tab — handle it normally.
- **iOS Map tab shows dark chrome on shot 04**: known caveat (the colorScheme lock at `ZoneMapScreen.swift:85`). The plan ships this as the intended interpretation; do not "fix" without checking with the user.

## Files you should know

- Orchestrator: `qa/srednabg_screenshots.py`
- Shot list: `qa/screenshots/shots.yaml` — edit to add/reorder/tweak shots
- Loader: `qa/screenshots/loader.py`
- GPS sequencer: `qa/screenshots/sequencer.py` (band tail durations live here)
- Output: `web/screenshots/{android,ios}/<NN>-<os>-<theme>-<lang>.png` (e.g. `01-android-light-bg.png`, `04-ios-dark-en.png`)
- Debug back-channels: Android `DebugControlReceiver` (FEED_POINT, SET_SETTING), iOS HTTP server at `127.0.0.1:47823` (`/inject`, `/setting`, `/mute`, `/tracking`)

## Always do

- Confirm platform before starting. Don't guess.
- Drive every cue promptly — the orchestrator's wall-clock matters for the average-speed calc inside the app, and a stalled cue queue can leave a Red-band shot with the wrong color.
- Quote the signal directory in your final message so the user can inspect cue/ack history if anything looked wrong.

## Never do

- Don't edit the produced PNGs. A downstream script handles store-asset framing.
- Don't run `/screenshot-app` without a booted device — it'll fail at preflight with a confusing message.
- Don't change `qa/screenshots/shots.yaml` to make a flaky shot "easier" — fix the underlying band determinism in `sequencer.py`.
