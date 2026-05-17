# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — store-asset framing post-processor.
#
# Takes the raw PNGs that /screenshot-app drops into
# web/screenshots/<platform>/NN-<platform>-<theme>-<lang>.png and composes
# Waze-style marketing frames (solid brand-color background + centered
# title text + smaller phone screenshot below with rounded corners and a
# thin black border) into web/screenshots/<platform>/framed/.
#
# Driven by the `frame:` block and per-shot `background` + `title` keys
# in qa/screenshots/shots.yaml. Capture and framing are intentionally
# decoupled — iterating on a title or color does NOT require re-driving
# the emulator.
#
# Usage:
#     python qa/srednabg_frame_screenshots.py <android|ios> [shot] [lang] \
#         [--theme light|dark] [--force]
#
# Examples:
#     # render exactly ONE PNG:
#     python qa/srednabg_frame_screenshots.py android 2 en --theme light
#
#     # render one shot, all langs, all themes:
#     python qa/srednabg_frame_screenshots.py android home-in-zone-green
#
#     # render everything:
#     python qa/srednabg_frame_screenshots.py android

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ImageDraw, ImageFont

# Allow `python qa/srednabg_frame_screenshots.py` from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qa.screenshots import loader
from qa.screenshots.loader import (
    ChromeMaskSpec,
    FrameConfig,
    FrameSpec,
    Shot,
    ShotConfig,
    SCREENSHOTS_ROOT,
    VALID_PLATFORMS,
)

VALID_LANGS = ("en", "bg")
VALID_THEMES = ("light", "dark")
MIN_TITLE_SIZE_PX = 64           # auto-shrink floor
SHRINK_STEP_PX = 8
MAX_SHRINK_RETRIES = 3
HARD_BOTTOM_MARGIN_PX = 80       # min gap below the phone thumbnail
MAX_VISUAL_LINES = 4             # cap before we start shrinking


# ---------------------------------------------------------------------------
# Job selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    shot: Shot
    spec: FrameSpec
    raw_path: Path
    lang: str
    theme: str
    platform: str
    out_path: Path


@dataclass(frozen=True)
class Skip:
    shot_nn: int
    shot_name: str
    lang: str
    theme: str
    reason: str


def select_jobs(
    cfg: ShotConfig,
    platform: str,
    shot_filter: Optional[str],
    lang_filter: Optional[str],
    theme: str,
    out_root: Path,
) -> tuple[list[Job], list[Skip]]:
    """Return (jobs to render, shots we intentionally skipped with reasons)."""
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"platform={platform!r} not in {VALID_PLATFORMS}")
    if cfg.frame is None:
        raise ValueError(
            "shots.yaml has no top-level `frame:` block — nothing to render. "
            "Add the frame config (font, sizes, canvas, colors) and re-run."
        )

    target_shots = _filter_shots(cfg, shot_filter)
    langs = (lang_filter,) if lang_filter else tuple(cfg.languages)

    jobs: list[Job] = []
    skips: list[Skip] = []
    for shot in target_shots:
        spec = shot.frame
        if spec is None or spec.background is None:
            skips.append(Skip(shot.nn, shot.name, "*", theme,
                              "no background/title in shots.yaml"))
            continue
        for lang in langs:
            title = spec.titles.get(lang)
            if not title:
                skips.append(Skip(shot.nn, shot.name, lang, theme,
                                  f"no title.{lang} in shots.yaml"))
                continue
            raw_path = (SCREENSHOTS_ROOT / platform /
                        f"{shot.nn:02d}-{platform}-{theme}-{lang}.png")
            if not raw_path.exists():
                skips.append(Skip(shot.nn, shot.name, lang, theme,
                                  f"raw PNG missing ({raw_path.name})"))
                continue
            out_path = (out_root / platform / "framed" /
                        f"{shot.nn:02d}-{theme}-{lang}.png")
            jobs.append(Job(shot, spec, raw_path, lang, theme, platform, out_path))
    return jobs, skips


def _filter_shots(cfg: ShotConfig, shot_filter: Optional[str]) -> list[Shot]:
    if shot_filter is None:
        return list(cfg.shots)
    try:
        return [cfg.by_index(int(shot_filter))]
    except (ValueError, KeyError):
        pass
    return [cfg.by_name(shot_filter)]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_job(job: Job, fc: FrameConfig, canvas: tuple[int, int]) -> None:
    W, H = canvas
    bg_rgb = _hex_to_rgb(_resolve_color(job.spec.background, fc.colors))
    text_rgb = _hex_to_rgb(fc.text_color)
    border_rgb = _hex_to_rgb(fc.phone_border_color)

    img = Image.new("RGB", (W, H), bg_rgb)
    draw = ImageDraw.Draw(img)

    title_text = job.spec.titles[job.lang]
    title_block_h, used_size = _draw_title(
        draw, fc, title_text, W, text_rgb,
    )
    title_bottom = fc.title_margin_top_px + title_block_h

    # Phone thumbnail — fit by width, then guard with height-fit.
    raw = Image.open(job.raw_path).convert("RGBA")
    _apply_chrome_mask(raw, fc.chrome_mask.get(job.platform))
    target_w = int(W * fc.phone_max_width_frac)
    target_h = round(raw.height * target_w / raw.width)
    available_h = H - title_bottom - fc.phone_margin_top_px - HARD_BOTTOM_MARGIN_PX
    if target_h > available_h:
        scale = available_h / raw.height
        target_w = int(raw.width * scale)
        target_h = int(raw.height * scale)
    if target_w <= 0 or target_h <= 0:
        raise ValueError(
            f"shot #{job.shot.nn} ({job.shot.name}, {job.lang}, {job.theme}): "
            f"title block ({title_block_h}px @ {used_size}px) leaves no room "
            f"for the phone thumbnail in {W}x{H} canvas — shorten the title "
            f"or raise frame.canvas."
        )
    thumb = raw.resize((target_w, target_h), Image.LANCZOS)

    # Rounded-corner mask applied as alpha.
    mask = Image.new("L", (target_w, target_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, target_w, target_h),
        radius=fc.phone_corner_radius_px,
        fill=255,
    )
    thumb.putalpha(mask)

    px = (W - target_w) // 2
    py = title_bottom + fc.phone_margin_top_px
    img.paste(thumb, (px, py), thumb)

    # Stroke the border on the canvas (not the alpha-masked thumb — that
    # produces jaggy corners). Use right/bottom = corner-1 to land on the
    # last filled pixel of the rounded mask.
    ImageDraw.Draw(img).rounded_rectangle(
        (px, py, px + target_w - 1, py + target_h - 1),
        radius=fc.phone_corner_radius_px,
        outline=border_rgb,
        width=fc.phone_border_px,
    )

    job.out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(job.out_path, format="PNG", optimize=True)


def _apply_chrome_mask(raw: Image.Image, spec: Optional[ChromeMaskSpec]) -> None:
    """Paint a solid band over the top `spec.top_px` rows of `raw` (in place).

    The band color is sampled from a 16-row by W/2-wide region centered
    horizontally at `spec.sample_y_frac` of `raw`. Per-channel median makes
    the sample robust against icons/labels that might land in the strip.
    No-op if `spec` is None (platform has no chrome_mask entry) or
    `spec.top_px == 0` (mask disabled for that platform).
    """
    if spec is None or spec.top_px <= 0:
        return
    W, H = raw.size
    y_center = max(0, min(H - 1, int(H * spec.sample_y_frac)))
    band_top = max(0, y_center - 8)
    band_bot = min(H, y_center + 8)
    x_left = W // 4
    x_right = 3 * W // 4
    sample = raw.crop((x_left, band_top, x_right, band_bot)).convert("RGB")
    px = list(sample.getdata())
    rs = sorted(p[0] for p in px)
    gs = sorted(p[1] for p in px)
    bs = sorted(p[2] for p in px)
    mid = len(px) // 2
    color = (rs[mid], gs[mid], bs[mid], 255)
    paint_h = min(spec.top_px, H)
    ImageDraw.Draw(raw).rectangle((0, 0, W, paint_h), fill=color)


def _draw_title(
    draw: ImageDraw.ImageDraw,
    fc: FrameConfig,
    text: str,
    canvas_w: int,
    text_rgb: tuple[int, int, int],
) -> tuple[int, int]:
    """Wrap, lay out, and draw the title; return (block_height_px, used_font_size_px).

    Auto-shrinks by SHRINK_STEP_PX up to MAX_SHRINK_RETRIES times when the
    wrapped text exceeds MAX_VISUAL_LINES. Raises if it still doesn't fit at
    MIN_TITLE_SIZE_PX.
    """
    font_path = str(REPO_ROOT / fc.font)
    size = fc.title_size_px
    max_text_w = canvas_w - 2 * fc.title_margin_x_px

    lines: list[str] = []
    font: Optional[ImageFont.FreeTypeFont] = None
    for attempt in range(MAX_SHRINK_RETRIES + 1):
        font = ImageFont.truetype(font_path, size)
        lines = _wrap_text(text, font, max_text_w)
        if len(lines) <= MAX_VISUAL_LINES and not _any_line_overflows(lines, font, max_text_w):
            break
        if size - SHRINK_STEP_PX < MIN_TITLE_SIZE_PX:
            break
        size -= SHRINK_STEP_PX
    assert font is not None
    if len(lines) > MAX_VISUAL_LINES or _any_line_overflows(lines, font, max_text_w):
        raise ValueError(
            f"title doesn't fit in canvas width {canvas_w}px even at "
            f"{size}px: {text!r}. Shorten the title or raise frame.canvas."
        )

    joined = "\n".join(lines)
    spacing_px = int(round(size * (fc.title_line_spacing - 1)))
    draw.multiline_text(
        (canvas_w / 2, fc.title_margin_top_px),
        joined,
        font=font,
        fill=text_rgb,
        anchor="ma",
        align="center",
        spacing=spacing_px,
    )
    # multiline_textbbox gives the bbox in canvas coords; subtract the top
    # margin to get the block height.
    bbox = draw.multiline_textbbox(
        (canvas_w / 2, fc.title_margin_top_px),
        joined,
        font=font,
        anchor="ma",
        align="center",
        spacing=spacing_px,
    )
    block_h = bbox[3] - fc.title_margin_top_px
    return block_h, size


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Pixel-wrap text by word using font.getlength(). Respects explicit '\\n'
    as a hard paragraph break; wraps each paragraph independently.
    """
    out: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            out.append("")
            continue
        current = words[0]
        for w in words[1:]:
            candidate = f"{current} {w}"
            if font.getlength(candidate) <= max_w:
                current = candidate
            else:
                out.append(current)
                current = w
        out.append(current)
    return out


def _any_line_overflows(lines: list[str], font: ImageFont.FreeTypeFont, max_w: int) -> bool:
    # A single word longer than max_w can't be split — surface that as overflow
    # so the auto-shrink loop kicks in.
    return any(font.getlength(line) > max_w for line in lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_color(value: str, palette: dict[str, str]) -> str:
    if value.startswith("#"):
        return value
    if value not in palette:
        raise ValueError(
            f"background={value!r} not in palette {sorted(palette.keys())}")
    return palette[value]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def _is_up_to_date(out: Path, raw: Path) -> bool:
    return out.exists() and out.stat().st_mtime > raw.stat().st_mtime


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="srednabg_frame_screenshots",
        description=(
            "Frame raw SrednaBG store PNGs into Waze-style marketing "
            "screenshots. See qa/screenshots/shots.yaml `frame:` block."
        ),
    )
    p.add_argument("platform", choices=VALID_PLATFORMS)
    p.add_argument("shot", nargs="?", default=None,
                   help="NN (1-based) or name slug. Omit to render all.")
    p.add_argument("lang", nargs="?", default=None, choices=(None, *VALID_LANGS),
                   help="Language code. Omit to render every language in shots.yaml.")
    p.add_argument("--theme", default="light", choices=VALID_THEMES,
                   help="System appearance the raw PNG was captured under "
                        "(default: light).")
    p.add_argument("--force", action="store_true",
                   help="Re-render even when the output is newer than the input.")
    args = p.parse_args(argv)

    cfg = loader.load()
    jobs, skips = select_jobs(
        cfg,
        platform=args.platform,
        shot_filter=args.shot,
        lang_filter=args.lang,
        theme=args.theme,
        out_root=SCREENSHOTS_ROOT,
    )

    if cfg.frame is None:
        # select_jobs raises in this case, but keep the type narrowing clean.
        return 2
    canvas = cfg.frame.canvas.get(args.platform)
    if canvas is None:
        print(f"error: shots.yaml frame.canvas has no entry for {args.platform!r}",
              file=sys.stderr)
        return 2

    t0 = time.monotonic()
    rendered: list[Path] = []
    up_to_date: list[Path] = []
    for job in jobs:
        if not args.force and _is_up_to_date(job.out_path, job.raw_path):
            up_to_date.append(job.out_path)
            continue
        render_job(job, cfg.frame, canvas)
        rendered.append(job.out_path)

    _report(rendered, up_to_date, skips, time.monotonic() - t0)

    return 0 if (rendered or up_to_date) else 2


def _report(
    rendered: Iterable[Path],
    up_to_date: Iterable[Path],
    skips: Iterable[Skip],
    elapsed: float,
) -> None:
    rendered = list(rendered)
    up_to_date = list(up_to_date)
    skips = list(skips)
    print(f"rendered {len(rendered)} framed PNG(s) in {elapsed:.1f}s "
          f"({len(up_to_date)} already up-to-date, {len(skips)} skipped)")
    for p in rendered:
        print(f"  + {p.relative_to(SCREENSHOTS_ROOT.parent.parent)}")
    if skips:
        print("skipped:")
        for s in skips:
            print(f"  - shot {s.shot_nn:02d} {s.shot_name} [{s.lang}/{s.theme}]: {s.reason}")


if __name__ == "__main__":
    sys.exit(main())
