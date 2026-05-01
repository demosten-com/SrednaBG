# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Loads YAML scenarios from `scenarios/bulk/` and `scenarios/representative/`.

YAML schema (kept minimal — anything more complex belongs in `scenarios/edge/`
as Python):

    name: trakiya-01-east @ 130 km/h
    zone_id: trakiya-01-east
    speed_kmh: 130
    approach_km: 2.0
    exit_km: 1.0
    hz: 1.0
    compression: 4.0           # wall-clock multiplier
    expect_enter: true
    expect_exit: true
    expect_avg_kmh: 130        # ±tolerance below
    avg_kmh_tolerance: 5
    forbid_in_zone_rebound: true
    settings: S1               # SettingsCombo id, optional
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .. import adb, settings as settings_mod
from ..assertions import expect, expect_in_order, expect_never, expect_crash_free, AssertionFailure
from ..drive import DrivePlan, parse_gpx, pump
from ..events import Crash, ZoneStateChange
from ..runner import RunContext, Scenario, Step, step_drive, step_lambda, step_wait

REPO_ROOT = Path(__file__).resolve().parents[2]
ZONES_JSON = REPO_ROOT / "scrapers" / "data" / "zones.json"
GPX_FIXTURES_DIR = REPO_ROOT / "qa" / "fixtures" / "gpx"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Tiny YAML loader for our flat schema. Avoids adding a PyYAML dep
    for simple key:value docs. Supports # comments, quoted strings,
    booleans, ints, floats."""
    out: dict[str, Any] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if not v:
            continue
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            out[k] = v[1:-1]
        elif v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        else:
            try:
                if "." in v:
                    out[k] = float(v)
                else:
                    out[k] = int(v)
            except ValueError:
                out[k] = v
    return out


@dataclass
class BulkScenarioSpec:
    name: str
    zone_id: str
    speed_kmh: float = 130.0
    approach_km: float = 2.0
    exit_km: float = 1.0
    hz: float = 1.0
    compression: float = 4.0
    expect_enter: bool = True
    expect_exit: bool = True
    expect_avg_kmh: Optional[float] = None
    avg_kmh_tolerance: float = 5.0
    forbid_in_zone_rebound: bool = True
    settings: Optional[str] = None


def _ensure_gpx(spec: BulkScenarioSpec) -> Path:
    """Generate per-zone GPX on demand using make_test_route.py (vendored
    behavior). Avoids shelling out to keep the harness stdlib-only."""
    GPX_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    out = GPX_FIXTURES_DIR / f"{spec.zone_id}_{int(spec.speed_kmh)}.gpx"
    if out.exists():
        return out
    # Lazy-import to avoid stdlib path mangling at module load.
    import importlib.util
    script_path = REPO_ROOT / "scrapers" / "scripts" / "make_test_route.py"
    spec_mod = importlib.util.spec_from_file_location("make_test_route", script_path)
    if not spec_mod or not spec_mod.loader:
        raise RuntimeError("could not load make_test_route.py")
    mod = importlib.util.module_from_spec(spec_mod)
    spec_mod.loader.exec_module(mod)

    zone = mod.load_zone(ZONES_JSON, spec.zone_id)
    centerline = [(p[0], p[1]) for p in zone["centerline"]]
    if len(centerline) < 2:
        raise RuntimeError(f"zone {spec.zone_id} has insufficient centerline")

    entry_bearing = mod.bearing_deg(centerline[1][0], centerline[1][1], centerline[0][0], centerline[0][1])
    exit_bearing = mod.bearing_deg(centerline[-2][0], centerline[-2][1], centerline[-1][0], centerline[-1][1])
    approach_start = mod.destination_point(centerline[0][0], centerline[0][1], entry_bearing, spec.approach_km * 1000)
    exit_end = mod.destination_point(centerline[-1][0], centerline[-1][1], exit_bearing, spec.exit_km * 1000)

    step_m = (spec.speed_kmh / 3.6) / spec.hz

    def resample(seg: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return list(mod.resample_polyline(seg, step_m))

    approach_pts = resample([approach_start, centerline[0]])
    centerline_pts = resample(centerline)
    exit_pts = resample([centerline[-1], exit_end])
    # Splice — keep boundary vertices explicit per make_test_route semantics
    pts = approach_pts + [centerline[0]] + centerline_pts[1:] + [centerline[-1]] + exit_pts[1:] + [exit_end]
    mod.emit_gpx(pts, spec.hz, out, name=f"{spec.zone_id}@{spec.speed_kmh}kmh")
    return out


def _approach_seconds(spec: BulkScenarioSpec) -> float:
    return (spec.approach_km * 1000) / (spec.speed_kmh / 3.6) / spec.compression


def build_scenario(spec: BulkScenarioSpec) -> Scenario:
    """Translate a spec into a runnable Scenario."""
    gpx_path = _ensure_gpx(spec)
    plan = parse_gpx(gpx_path).compressed(spec.compression)

    def setup_step(ctx: RunContext) -> None:
        # MainActivity must be foregrounded before start-foreground-service
        # is allowed under Android 12+ background-start restrictions.
        adb.start_main()
        time.sleep(2.0)
        # Apply settings combo if specified
        if spec.settings:
            combo = next((c for c in settings_mod.ALL_COMBOS if c.id == spec.settings), None)
            if combo:
                combo.apply(ctx.obs)
                time.sleep(0.5)
        settings_mod.start_tracking()
        # Wait for the service to register location updates so the first
        # geo fix is actually delivered to the detector.
        time.sleep(2.5)
        ctx.obs.clear()

    def assert_enter(ctx: RunContext) -> None:
        if not spec.expect_enter:
            return
        within = _approach_seconds(spec) + 30
        expect(
            ctx.obs,
            ZoneStateChange,
            where=lambda e: e.new == "InZone" and e.prev == "Outside",
            within_s=within,
            description=f"zone entry for {spec.zone_id}",
        )

    def assert_exit(ctx: RunContext) -> None:
        if not spec.expect_exit:
            return
        within = (plan.duration_ms / 1000.0) + 30
        expect_in_order(
            ctx.obs,
            [
                (ZoneStateChange, lambda e: e.new == "Exiting"),
            ],
            within_s=within,
            description=f"zone exit for {spec.zone_id}",
        )

    def teardown(ctx: RunContext) -> None:
        settings_mod.stop_tracking()
        expect_crash_free(ctx.obs)

    steps: list[Step] = [
        step_lambda("setup", setup_step),
        step_drive(plan, compression=1.0),  # already compressed
        step_lambda("assert_enter", assert_enter),
        step_lambda("assert_exit", assert_exit),
    ]
    return Scenario(name=spec.name, steps=steps, teardown=teardown,
                    timeout_s=plan.duration_ms / 1000 + 60)


def load_specs_from_dir(dir_path: Path) -> list[BulkScenarioSpec]:
    out: list[BulkScenarioSpec] = []
    for p in sorted(dir_path.glob("*.yaml")):
        d = _load_yaml(p)
        out.append(BulkScenarioSpec(
            name=str(d.get("name") or p.stem),
            zone_id=str(d["zone_id"]),
            speed_kmh=float(d.get("speed_kmh", 130.0)),
            approach_km=float(d.get("approach_km", 2.0)),
            exit_km=float(d.get("exit_km", 1.0)),
            hz=float(d.get("hz", 1.0)),
            compression=float(d.get("compression", 4.0)),
            expect_enter=bool(d.get("expect_enter", True)),
            expect_exit=bool(d.get("expect_exit", True)),
            expect_avg_kmh=float(d["expect_avg_kmh"]) if "expect_avg_kmh" in d else None,
            avg_kmh_tolerance=float(d.get("avg_kmh_tolerance", 5.0)),
            forbid_in_zone_rebound=bool(d.get("forbid_in_zone_rebound", True)),
            settings=str(d["settings"]) if "settings" in d else None,
        ))
    return out
