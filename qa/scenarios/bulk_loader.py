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

import hashlib
import json
import queue
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .. import device as device_mod, settings as settings_mod
from ..assertions import expect, expect_in_order, expect_never, expect_crash_free, AssertionFailure
from ..drive import DrivePlan, parse_gpx, pump
from ..events import Crash, DisplaySpeed, ZoneStateChange
from ..log_observer import LogObserver
from ..runner import RunContext, Scenario, Step, step_drive, step_lambda, step_wait

REPO_ROOT = Path(__file__).resolve().parents[2]
# The single source of truth both apps bundle (see root CLAUDE.md);
# scrapers/data/zones.json is a sibling copy kept in sync by the refresh
# script, but everything in qa/ reads the canonical file.
ZONES_JSON = REPO_ROOT / "backend" / "data" / "zones.json"
GPX_FIXTURES_DIR = REPO_ROOT / "qa" / "fixtures" / "gpx"

# Parsed zones.json, cached per (path, mtime) so 72 bulk scenarios don't
# re-read the 1.4 MB file.
_zones_cache: dict[tuple[str, float], dict[str, dict]] = {}


def _zones_by_id() -> dict[str, dict]:
    key = (str(ZONES_JSON), ZONES_JSON.stat().st_mtime)
    if key not in _zones_cache:
        _zones_cache.clear()
        data = json.loads(ZONES_JSON.read_text(encoding="utf-8"))
        zones = data["zones"] if isinstance(data, dict) else data
        _zones_cache[key] = {z["id"]: z for z in zones}
    return _zones_cache[key]


def _route_hash(zone: dict, spec: "BulkScenarioSpec") -> str:
    """Deterministic short hash of everything that shapes the generated GPX —
    the zone geometry plus the route parameters. Embedded in the cached GPX
    filename so a zones.json change (e.g. a centerline realignment) or a spec
    change regenerates the fixture instead of silently reusing stale geometry."""
    payload = json.dumps(
        {
            # Bump when the route-construction algorithm itself changes, so
            # cached fixtures from the old generator regenerate. gen 2:
            # approach/exit bearings anchored 300 m along the arc (jog-proof).
            "gen": 2,
            "centerline": zone.get("centerline"),
            "start": zone.get("start"),
            "end": zone.get("end"),
            "speed_kmh": spec.speed_kmh,
            "approach_km": spec.approach_km,
            "exit_km": spec.exit_km,
            "hz": spec.hz,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


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
    behavior). Avoids shelling out to keep the harness stdlib-only.

    The cached filename embeds `_route_hash` (zone geometry + route params),
    so the cache self-invalidates when zones.json or the spec changes —
    stale same-prefix fixtures from earlier data are removed on regeneration."""
    GPX_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    zone = _zones_by_id().get(spec.zone_id)
    if zone is None:
        raise RuntimeError(f"zone {spec.zone_id} not found in {ZONES_JSON}")
    prefix = f"{spec.zone_id}_{int(spec.speed_kmh)}"
    out = GPX_FIXTURES_DIR / f"{prefix}_{_route_hash(zone, spec)}.gpx"
    if out.exists():
        return out
    for stale in GPX_FIXTURES_DIR.glob(f"{prefix}*.gpx"):
        stale.unlink(missing_ok=True)
    # Lazy-import to avoid stdlib path mangling at module load.
    import importlib.util
    script_path = REPO_ROOT / "scrapers" / "scripts" / "make_test_route.py"
    spec_mod = importlib.util.spec_from_file_location("make_test_route", script_path)
    if not spec_mod or not spec_mod.loader:
        raise RuntimeError("could not load make_test_route.py")
    mod = importlib.util.module_from_spec(spec_mod)
    spec_mod.loader.exec_module(mod)

    centerline = [(p[0], p[1]) for p in zone["centerline"]]
    if len(centerline) < 2:
        raise RuntimeError(f"zone {spec.zone_id} has insufficient centerline")

    def outward_bearing(at_start: bool, anchor_m: float = 300.0) -> float:
        """Bearing pointing OUTWARD past the zone boundary, anchored ~300 m
        along the polyline arc instead of the first/last micro-segment.

        Real centerlines jog backward at their very first vertex and hook at
        their tail (both documented data quirks). Deriving the approach from
        cl[0]->cl[1] then aims the 2 km lead-in INTO the zone along the road
        — forward drives approach the start backwards and pivot 180° on it
        (the observed snap-enter/exit/re-enter artifact), and reversed
        wrong-direction drives end with a leg that legitimately travels the
        zone's direction, which the engine correctly admits."""
        pts = centerline if at_start else list(reversed(centerline))
        anchor = pts[-1]
        acc = 0.0
        for a, b in zip(pts, pts[1:]):
            acc += mod.haversine_m(a[0], a[1], b[0], b[1])
            if acc >= anchor_m:
                anchor = b
                break
        return mod.bearing_deg(anchor[0], anchor[1], pts[0][0], pts[0][1])

    entry_bearing = outward_bearing(at_start=True)
    exit_bearing = outward_bearing(at_start=False)
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
        # Foreground the app before issuing start-tracking. On Android this
        # satisfies the background-start restriction; on iOS it ensures the
        # CoreLocation pipeline is alive and Live Activities can be created.
        device_mod.current().start_main()
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

    def assert_drive(ctx: RunContext) -> None:
        # The drive step completed before this runs, so all events are already
        # buffered (modulo log-stream lag) — drain once, assert from the list.
        # A single pass lets the avg-speed check see the DisplaySpeed events
        # that a chained expect() would have consumed and discarded. When an
        # exit is expected, wait for the terminal Exiting transition rather than
        # a fixed cut-off, so a lagging log tail can't drop it.
        terminal = ((lambda e: isinstance(e, ZoneStateChange) and e.new == "Exiting")
                    if spec.expect_exit else None)
        events = _drain_buffered(ctx.obs, until=terminal)
        changes = [e for e in events if isinstance(e, ZoneStateChange)]

        def transitions() -> str:
            toks = [f"{e.prev}->{e.new}:{e.zone}" for e in changes]
            return " ".join(toks) or "(no zone state changes)"

        entry_idx = next((i for i, e in enumerate(changes)
                          if e.prev == "Outside" and e.new == "InZone"), None)
        if entry_idx is None:
            if spec.expect_enter:
                raise AssertionFailure(
                    f"no zone entry observed for {spec.zone_id} — {transitions()}",
                    ctx.obs)
            return
        entry = changes[entry_idx]

        # Like the original bulk asserts, enter/exit don't pin the zone *id*
        # (direction validation is validate-zones.sh's job — the approach can
        # legitimately clip an adjacent zone first); the flap check below is
        # per-id, so it stays meaningful either way.
        exit_ev = next((e for e in changes[entry_idx + 1:] if e.new == "Exiting"), None)
        if spec.expect_exit and exit_ev is None:
            raise AssertionFailure(
                f"no zone exit observed for {spec.zone_id} — {transitions()}",
                ctx.obs)

        if spec.forbid_in_zone_rebound:
            # Re-entering a zone after its own Exiting on a one-way drive is
            # the InZone<->Exiting flap the engine's exit hysteresis prevents.
            exited: set[str] = set()
            for e in changes:
                if e.new == "Exiting" and e.zone != "-":
                    exited.add(e.zone)
                elif e.new == "InZone" and e.zone in exited:
                    raise AssertionFailure(
                        f"in-zone rebound: {e.zone} re-entered after exiting "
                        f"(flap) — {transitions()}",
                        ctx.obs)

        if spec.expect_avg_kmh is not None and exit_ev is not None:
            in_zone = [e.kmh for e in events
                       if isinstance(e, DisplaySpeed)
                       and entry.monotonic_ms <= e.monotonic_ms <= exit_ev.monotonic_ms]
            if not in_zone:
                raise AssertionFailure(
                    f"expect_avg_kmh set but no DisplaySpeed events between "
                    f"entry and exit of {spec.zone_id}", ctx.obs)
            avg = sum(in_zone) / len(in_zone)
            if abs(avg - spec.expect_avg_kmh) > spec.avg_kmh_tolerance:
                raise AssertionFailure(
                    f"average in-zone speed {avg:.1f} km/h outside "
                    f"{spec.expect_avg_kmh}±{spec.avg_kmh_tolerance} km/h "
                    f"({len(in_zone)} fixes)", ctx.obs)

    def teardown(ctx: RunContext) -> None:
        settings_mod.stop_tracking()
        expect_crash_free(ctx.obs)

    steps: list[Step] = [
        step_lambda("setup", setup_step),
        step_drive(plan, compression=1.0),  # already compressed
        step_lambda("assert_drive", assert_drive),
    ]
    return Scenario(name=spec.name, steps=steps, teardown=teardown,
                    timeout_s=plan.duration_ms / 1000 + 60)


def _drain_buffered(obs: LogObserver, *, quiet_s: float = 1.0,
                    max_wait_s: float = 20.0, until=None) -> list:
    """Collect the events buffered for a completed drive.

    When `until` is given, keep draining past quiet periods until an event
    satisfies it (then capture one final `quiet_s` tail) or `max_wait_s`
    elapses — so a lagging log stream (slow iOS `log stream` attach, a busy
    emulator, a GC pause) can't drop the terminal `Exiting` / trailing
    `DisplaySpeed` events the assertion needs by hitting a fixed cut-off too
    early. Without `until` it falls back to the original behaviour: stop after
    `quiet_s` with no new event (the higher `max_wait_s` is just a safety
    ceiling)."""
    out: list = []
    deadline = time.monotonic() + max_wait_s
    quiet_deadline = time.monotonic() + quiet_s
    terminal_seen = until is None
    while time.monotonic() < deadline:
        try:
            ev = obs.queue.get(timeout=0.2)
        except queue.Empty:
            # Quiet slice: stop once the terminal is satisfied (or none was
            # required) and the quiet window has elapsed.
            if terminal_seen and time.monotonic() >= quiet_deadline:
                break
            continue
        out.append(ev)
        quiet_deadline = time.monotonic() + quiet_s
        if not terminal_seen and until(ev):
            terminal_seen = True
    return out


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
