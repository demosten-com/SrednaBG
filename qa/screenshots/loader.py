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

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

SHOTS_YAML = Path(__file__).resolve().parent / "shots.yaml"

VALID_TABS = ("home", "map", "settings")
VALID_BANDS = ("outside", "green", "yellow", "red", "none")
VALID_MAP_THEMES = ("light", "dark", "auto")


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


@dataclass(frozen=True)
class ShotConfig:
    zone_id: str
    languages: list[str]
    shots: list[Shot]

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
        ))

    return ShotConfig(zone_id=zone_id, languages=languages, shots=shots)


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
