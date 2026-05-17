# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa.screenshots

"""Parse qa/screenshots/shots.yaml into typed Shot objects.

Thin: just YAML → dataclass + a couple of selectors. All editing happens
in the YAML; this loader's only job is to validate and surface friendly
errors when a shot is missing or mis-typed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import yaml

SHOTS_YAML = Path(__file__).resolve().parent / "shots.yaml"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS_ROOT = REPO_ROOT / "web" / "screenshots"

VALID_TABS = ("home", "map", "settings")
VALID_BANDS = ("outside", "green", "yellow", "red", "none")
VALID_MAP_THEMES = ("light", "dark", "auto")
VALID_PLATFORMS = ("android", "ios")


@dataclass(frozen=True)
class FrameSpec:
    background: Optional[str]  # palette key (from FrameConfig.colors) OR "#RRGGBB"
    titles: dict[str, str]     # lang code → title text (may contain literal "\n")


@dataclass(frozen=True)
class ChromeMaskSpec:
    # Paint a solid band over the top `top_px` rows of the raw screenshot to
    # hide the OS status bar. The band's color is sampled at render time from
    # the bottom tab bar — tab-bar bg is uniform per theme (light/dark), and
    # the status bar itself is unreliable (map shots draw under a transparent
    # status bar). top_px == 0 disables the mask for the platform.
    top_px: int
    sample_y_frac: float       # vertical position in (0, 1) to sample from


@dataclass(frozen=True)
class FrameConfig:
    font: str                          # repo-relative path to TTF
    title_size_px: int
    title_line_spacing: float
    title_margin_top_px: int
    title_margin_x_px: int
    phone_margin_top_px: int
    phone_max_width_frac: float
    phone_corner_radius_px: int
    phone_border_px: int
    phone_border_color: str            # "#RRGGBB"
    text_color: str                    # "#RRGGBB"
    colors: dict[str, str]             # palette key → "#RRGGBB"
    canvas: dict[str, tuple[int, int]] # platform → (width, height)
    chrome_mask: dict[str, ChromeMaskSpec] = field(default_factory=dict)


@dataclass(frozen=True)
class Shot:
    nn: int  # 1-based position in the YAML
    name: str
    description: str
    tab: str
    band: str
    cur_speed_kmh: Optional[float]
    map_heading_up: Optional[bool]
    map_theme_mode: Optional[str]
    map_zoom_override: Optional[float]
    max_now_override: Optional[int]
    frame: Optional[FrameSpec] = None


@dataclass(frozen=True)
class ShotConfig:
    zone_id: str
    languages: list[str]
    shots: list[Shot]
    frame: Optional[FrameConfig] = None

    def by_index(self, nn: int) -> Shot:
        for s in self.shots:
            if s.nn == nn:
                return s
        raise KeyError(f"no shot with nn={nn} (have {[s.nn for s in self.shots]})")

    def by_name(self, name: str) -> Shot:
        for s in self.shots:
            if s.name == name:
                return s
        raise KeyError(f"no shot named {name!r} "
                       f"(have {[s.name for s in self.shots]})")

    def framable(
        self,
        platform: str,
        lang: str,
        theme: str,
        screenshots_root: Path = SCREENSHOTS_ROOT,
    ) -> Iterator[tuple[Shot, FrameSpec, Path]]:
        """Yield (shot, spec, raw_png_path) for every shot that has both a
        title for `lang` and a `background`, and whose raw PNG exists on disk.
        Other shots are silently skipped — callers may iterate `self.shots`
        themselves if they want to surface the skip reason.
        """
        if platform not in VALID_PLATFORMS:
            raise ValueError(f"platform={platform!r} not in {VALID_PLATFORMS}")
        for s in self.shots:
            spec = s.frame
            if spec is None or spec.background is None:
                continue
            title = spec.titles.get(lang)
            if not title:
                continue
            raw = screenshots_root / platform / (
                f"{s.nn:02d}-{platform}-{theme}-{lang}.png"
            )
            if not raw.exists():
                continue
            yield s, spec, raw


def load(path: Path = SHOTS_YAML) -> ShotConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    zone_id = raw.get("zone_id")
    if not isinstance(zone_id, str) or not zone_id:
        raise ValueError(f"{path}: zone_id must be a non-empty string")
    languages = raw.get("languages", ["en", "bg"])
    if not isinstance(languages, list) or not all(isinstance(x, str) for x in languages):
        raise ValueError(f"{path}: languages must be a list of strings")
    shots_raw = raw.get("shots")
    if not isinstance(shots_raw, list) or not shots_raw:
        raise ValueError(f"{path}: shots must be a non-empty list")

    frame_cfg = _parse_frame(raw.get("frame"), path)
    palette_keys = set(frame_cfg.colors.keys()) if frame_cfg else set()

    shots: list[Shot] = []
    for i, sr in enumerate(shots_raw, start=1):
        if not isinstance(sr, dict):
            raise ValueError(f"{path}: shot #{i} must be a mapping")
        name = sr.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{path}: shot #{i} missing 'name'")
        tab = sr.get("tab")
        if tab not in VALID_TABS:
            raise ValueError(f"{path}: shot {name!r} tab={tab!r} not in {VALID_TABS}")
        band = sr.get("band")
        if band not in VALID_BANDS:
            raise ValueError(f"{path}: shot {name!r} band={band!r} not in {VALID_BANDS}")
        mtm = sr.get("map_theme_mode")
        if mtm is not None and mtm not in VALID_MAP_THEMES:
            raise ValueError(f"{path}: shot {name!r} map_theme_mode={mtm!r} "
                             f"not in {VALID_MAP_THEMES}")
        cur_speed = sr.get("cur_speed_kmh")
        if band == "outside" and cur_speed is None:
            raise ValueError(f"{path}: shot {name!r} band=outside requires cur_speed_kmh")
        shots.append(Shot(
            nn=i,
            name=name,
            description=str(sr.get("description", "")),
            tab=tab,
            band=band,
            cur_speed_kmh=float(cur_speed) if cur_speed is not None else None,
            map_heading_up=_as_bool_or_none(sr.get("map_heading_up")),
            map_theme_mode=mtm,
            map_zoom_override=_as_float_or_none(sr.get("map_zoom_override")),
            max_now_override=_as_int_or_none(sr.get("max_now_override")),
            frame=_parse_frame_spec(sr, name, palette_keys, path),
        ))

    return ShotConfig(zone_id=zone_id, languages=languages, shots=shots, frame=frame_cfg)


def _parse_frame(raw, path: Path) -> Optional[FrameConfig]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level 'frame' must be a mapping")
    try:
        font = str(raw["font"])
        title_size_px = int(raw["title_size_px"])
        title_line_spacing = float(raw.get("title_line_spacing", 1.15))
        title_margin_top_px = int(raw.get("title_margin_top_px", 140))
        title_margin_x_px = int(raw.get("title_margin_x_px", 80))
        phone_margin_top_px = int(raw.get("phone_margin_top_px", 80))
        phone_max_width_frac = float(raw.get("phone_max_width_frac", 0.80))
        phone_corner_radius_px = int(raw.get("phone_corner_radius_px", 56))
        phone_border_px = int(raw.get("phone_border_px", 4))
        phone_border_color = _as_hex_color(raw.get("phone_border_color", "#000000"))
        text_color = _as_hex_color(raw.get("text_color", "#000000"))
        colors_raw = raw.get("colors", {})
        if not isinstance(colors_raw, dict) or not colors_raw:
            raise ValueError("frame.colors must be a non-empty mapping")
        colors = {str(k): _as_hex_color(v) for k, v in colors_raw.items()}
        canvas_raw = raw.get("canvas", {})
        if not isinstance(canvas_raw, dict) or not canvas_raw:
            raise ValueError("frame.canvas must be a non-empty mapping (platform → [W, H])")
        canvas: dict[str, tuple[int, int]] = {}
        for plat, dims in canvas_raw.items():
            if plat not in VALID_PLATFORMS:
                raise ValueError(
                    f"frame.canvas key {plat!r} not in {VALID_PLATFORMS}")
            if not (isinstance(dims, (list, tuple)) and len(dims) == 2
                    and all(isinstance(d, int) and d > 0 for d in dims)):
                raise ValueError(
                    f"frame.canvas[{plat}] must be [width, height] positive ints")
            canvas[plat] = (int(dims[0]), int(dims[1]))
    except KeyError as e:
        raise ValueError(f"{path}: frame missing required key {e}") from None
    chrome_mask = _parse_chrome_mask(raw.get("chrome_mask"), path)
    return FrameConfig(
        font=font,
        title_size_px=title_size_px,
        title_line_spacing=title_line_spacing,
        title_margin_top_px=title_margin_top_px,
        title_margin_x_px=title_margin_x_px,
        phone_margin_top_px=phone_margin_top_px,
        phone_max_width_frac=phone_max_width_frac,
        phone_corner_radius_px=phone_corner_radius_px,
        phone_border_px=phone_border_px,
        phone_border_color=phone_border_color,
        text_color=text_color,
        colors=colors,
        canvas=canvas,
        chrome_mask=chrome_mask,
    )


def _parse_chrome_mask(raw, path: Path) -> dict[str, ChromeMaskSpec]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: frame.chrome_mask must be a mapping")
    out: dict[str, ChromeMaskSpec] = {}
    for plat, entry in raw.items():
        if plat not in VALID_PLATFORMS:
            raise ValueError(
                f"{path}: frame.chrome_mask key {plat!r} not in {VALID_PLATFORMS}")
        if not isinstance(entry, dict):
            raise ValueError(
                f"{path}: frame.chrome_mask[{plat}] must be a mapping")
        top_px = entry.get("top_px", 0)
        if not isinstance(top_px, int) or isinstance(top_px, bool) or top_px < 0:
            raise ValueError(
                f"{path}: frame.chrome_mask[{plat}].top_px must be a non-negative int")
        sample_y_frac = entry.get("sample_y_frac", 0.96)
        if not isinstance(sample_y_frac, (int, float)) or not (0.0 < sample_y_frac < 1.0):
            raise ValueError(
                f"{path}: frame.chrome_mask[{plat}].sample_y_frac must be in (0, 1)")
        out[plat] = ChromeMaskSpec(top_px=top_px, sample_y_frac=float(sample_y_frac))
    return out


def _parse_frame_spec(
    sr: dict,
    shot_name: str,
    palette_keys: set[str],
    path: Path,
) -> Optional[FrameSpec]:
    bg = sr.get("background")
    titles_raw = sr.get("title")
    if bg is None and titles_raw is None:
        return None
    if bg is not None:
        if not isinstance(bg, str) or not bg:
            raise ValueError(f"{path}: shot {shot_name!r} background must be a non-empty string")
        if not bg.startswith("#"):
            # palette key
            if bg not in palette_keys:
                raise ValueError(
                    f"{path}: shot {shot_name!r} background={bg!r} not in "
                    f"frame.colors keys {sorted(palette_keys)}")
        else:
            _as_hex_color(bg)  # validates format
    titles: dict[str, str] = {}
    if titles_raw is not None:
        if not isinstance(titles_raw, dict):
            raise ValueError(
                f"{path}: shot {shot_name!r} title must be a mapping {{lang: text}}")
        for lang, text in titles_raw.items():
            if not isinstance(lang, str) or not isinstance(text, str):
                raise ValueError(
                    f"{path}: shot {shot_name!r} title entries must be str → str")
            titles[lang] = text
    return FrameSpec(background=bg, titles=titles)


def _as_hex_color(v) -> str:
    if not isinstance(v, str) or len(v) != 7 or v[0] != "#":
        raise ValueError(f"expected '#RRGGBB' hex color, got {v!r}")
    try:
        int(v[1:], 16)
    except ValueError:
        raise ValueError(f"expected '#RRGGBB' hex color, got {v!r}") from None
    return v


def _as_bool_or_none(v) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    raise ValueError(f"expected bool or null, got {v!r}")


def _as_float_or_none(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    raise ValueError(f"expected number or null, got {v!r}")


def _as_int_or_none(v) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError(f"expected integer or null, got bool {v!r}")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    raise ValueError(f"expected integer or null, got {v!r}")
