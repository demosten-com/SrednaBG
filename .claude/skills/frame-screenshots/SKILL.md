---
name: frame-screenshots
description: Frame raw SrednaBG store screenshots into Waze-style marketing PNGs (solid background + centered title + smaller phone screenshot with rounded corners + thin black border). Use when the user says "/frame-screenshots", "frame the screenshots", "make store frames", "rebuild marketing screenshots", or asks to compose store-asset framed screenshots from already-captured raw PNGs. Does NOT need an emulator — operates only on PNGs already in `web/screenshots/<platform>/`.
---

# frame-screenshots — store-asset compositor

You are driving the offline post-processor that turns the raw PNGs `/screenshot-app` captured (under `web/screenshots/<platform>/`) into Waze-style framed store screenshots. The renderer is `qa/srednabg_frame_screenshots.py`. The titles, background colors, font, sizes, and canvas dimensions all live in `qa/screenshots/shots.yaml` under the `frame:` block and per-shot `background` + `title` keys.

Your job: ask which platform if missing, ensure deps are installed, run the renderer, report the produced PNGs.

**This skill never touches the emulator/Simulator.** If the user has not yet captured raw PNGs (or wants new ones), they need `/screenshot-app` first.

## Inputs you accept

The user invokes you as `/frame-screenshots <android|ios> [shot] [lang] [--theme light|dark] [--force]`:

- `android` / `ios` — required. Which platform's raw PNGs to frame.
- `shot` — optional. Either an `NN` (1-based) or a `name` slug from `shots.yaml` (e.g. `home-in-zone-green`). Omit to frame every shot that has both `title` + `background` defined.
- `lang` — optional `en` / `bg`. Omit to render every language listed in `shots.yaml`'s `languages:`.
- `--theme light|dark` — optional. Selects which captured PNG to use as input (matches the suffix `/screenshot-app` writes). Default `light`.
- `--force` — optional. Re-render even when the output is newer than the input.

If the user typed just `/frame-screenshots` (no platform), **ask** which platform — there's no safe default.

**Single-shot iteration is the primary workflow.** Re-running on one shot while tweaking its title or color in `shots.yaml` is cheap and fast — no emulator involved. Examples:

```bash
# Render exactly ONE PNG (shot #2, English, light theme):
python qa/srednabg_frame_screenshots.py android 2 en --theme light

# Render one shot in both languages, both themes (typically up to 4 PNGs):
python qa/srednabg_frame_screenshots.py android home-in-zone-green

# Render everything that has both `title` and `background` and a raw PNG:
python qa/srednabg_frame_screenshots.py android
```

## Pre-flight (always)

Run **one** check before invoking the renderer:

```bash
python -c "import PIL, yaml" 2>/dev/null
```

If this exits non-zero, tell the user:

> Install dependencies first: `pip install -r qa/requirements.txt` (adds Pillow + PyYAML, ~6 MB).

…then stop. Do not try to install on the user's behalf — they may want a venv.

There is **no device check**. No emulator. No Simulator. This skill is offline.

## Running the renderer

Spawn it in the **foreground** (no cue loop, no background work):

```bash
python qa/srednabg_frame_screenshots.py <platform> [shot] [lang] [--theme light|dark] [--force]
```

Pass the user's args through verbatim. Outputs land under `web/screenshots/<platform>/framed/NN-<theme>-<lang>.png`.

## After it finishes

The script prints `rendered N framed PNG(s) in Xs (Y already up-to-date, Z skipped)` followed by:
- one line per rendered PNG (`+ web/screenshots/<platform>/framed/...`),
- one line per skip (`- shot NN <name> [<lang>/<theme>]: <reason>`).

Report concisely (cap at 150 words):
- One-line headline: rendered count, up-to-date count, skipped count, elapsed time.
- List the filenames (not full paths) that were freshly rendered.
- **Surface every skipped shot by name + reason.** Common reasons are "no title.<lang> in shots.yaml" (just author the title), "no background/title in shots.yaml" (intentionally not framed), or "raw PNG missing" (user needs to run `/screenshot-app` first for that combination).
- If the script raised `ValueError` (title overflow, missing canvas, etc.), surface the error message verbatim — they're authoring errors and the script's message is self-explanatory.

## Failure triage

- **`ModuleNotFoundError: No module named 'PIL'`** → user skipped pre-flight. Tell them to `pip install -r qa/requirements.txt`.
- **`title doesn't fit in canvas width ... even at <N>px`** → the title is too long even after the renderer auto-shrunk it. The user must either shorten `title.<lang>` in `shots.yaml` or insert a hard `\n` to break it earlier.
- **`background=<X> not in palette`** → unknown palette key. The user must either add `<X>` to `frame.colors:` in `shots.yaml` or use a literal `#RRGGBB` value.
- **0 rendered, 0 up-to-date, all skipped "raw PNG missing"** → the user hasn't run `/screenshot-app <platform>` for this theme yet (or didn't run it in the language they're asking for). Direct them to `/screenshot-app` first.
- **Cyrillic shows as `.notdef` boxes (empty squares)** → the bundled `qa/screenshots/fonts/Nunito-Bold.ttf` is missing or corrupt. Re-instance from the variable font in the googlefonts/nunito GitHub repo (one-time `fontTools.varLib.instancer.instantiateVariableFont` at `wght=700`).

## Files you should know

- Renderer: `qa/srednabg_frame_screenshots.py`
- Shot list + frame config: `qa/screenshots/shots.yaml`
- Loader: `qa/screenshots/loader.py` (adds `FrameConfig`, `FrameSpec`, `ShotConfig.framable()`)
- Font: `qa/screenshots/fonts/Nunito-Bold.ttf` (SIL OFL 1.1; license at `LICENSE-OFL.txt`)
- Output: `web/screenshots/{android,ios}/framed/NN-<theme>-<lang>.png`

## Always do

- Confirm platform before starting. Don't guess.
- Pass `--force` through if the user asked for it; otherwise the renderer's mtime check will skip unchanged outputs (fast iteration on titles works because Pillow rewrites the PNG, bumping the mtime).
- Surface every skip line in your final summary — silent skips defeat the whole point of an iterative compositor.

## Never do

- Don't run `/screenshot-app` from this skill. Capture and framing are deliberately separate. If raw PNGs are missing, tell the user; don't invoke the emulator harness.
- Don't write anywhere outside `web/screenshots/<platform>/framed/`. The renderer enforces this — don't try to "fix up" the raw inputs.
- Don't put the word "Android" (or "Андроид") into any title meant for an iOS shot — iOS-facing strings must not mention Android (per project memory).
- Don't edit `shots.yaml` to make a tight-fit title "work" by hacking `frame.canvas` larger than the store's required dimensions. Shorten the title or split with `\n` instead.
