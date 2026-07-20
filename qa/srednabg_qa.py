#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Entry point for the SrednaBG QA harness.

Usage (from repo root):

    python qa/srednabg_qa.py --suite smoke
    python qa/srednabg_qa.py --suite representative
    python qa/srednabg_qa.py --suite full-zones
    python qa/srednabg_qa.py --suite scenarios
    python qa/srednabg_qa.py --suite sync
    python qa/srednabg_qa.py --suite ui
    python qa/srednabg_qa.py --suite nightly

Exit code is 0 when all scenarios passed, 1 otherwise. Reports land in
qa/reports/<suite>-<timestamp>/ (junit.xml + summary.md + screenshots/).
"""

from __future__ import annotations

import argparse
import importlib
import signal
import sys
from pathlib import Path

# Allow running both as `python qa/srednabg_qa.py` and `python -m qa.srednabg_qa`
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from qa._preflight import require  # noqa: E402

require("yaml")

from qa import device as device_mod  # noqa: E402
from qa.report import write_reports  # noqa: E402
from qa.runner import Scenario, SuiteRunner  # noqa: E402
from qa.scenarios.bulk_loader import build_scenario, load_specs_from_dir  # noqa: E402

REPORTS_ROOT = _HERE / "reports"
BULK_DIR = _HERE / "scenarios" / "bulk"

# Which location source the installed flavor is expected to select, set from
# the --flavor CLI arg before suites are built: "system" (aosp), "fused" (gms),
# or None (auto — record-only, don't pin the flavor). Read by the
# location.source_selected scenario prepended to smoke + representative.
EXPECTED_LOCATION_SOURCE: str | None = None
_FLAVOR_TO_SOURCE = {"aosp": "system", "gms": "fused", "auto": None}
REPRESENTATIVE_DIR = _HERE / "scenarios" / "representative"
EDGE_DIR = _HERE / "scenarios" / "edge"
SYNC_DIR = _HERE / "scenarios" / "sync"

EDGE_SCENARIOS = [
    "stop_in_zone",
    "gps_dropout",
    "wrong_direction",
    "u_turn",
    "vehicle_swap",
    "vehicle_type_limit_badge",
    "over_limit_recovery",
    "off_ramp",
    "cold_start_spike",
    "speed_decay_after_stop",
    "auto_stop",
    "stop_silences_tts",
    "tts_cold_start_leadin",
    "dense_centerline",
    "noisy_fix_rejected",
]
# Edge scenarios that exercise an Android-only code path and would never pass on
# iOS, so they're skipped under `--platform ios` rather than failed (same
# philosophy as the location-source flavor tripwire prefix):
#   - `noisy_fix_rejected` tests the Android service's MAX_ACCURACY_M gate; iOS
#     has no equivalent (CoreLocation pre-filters).
#   - `cold_start_spike` reproduces an Android `LocationTrackingService.kt`
#     speed-inference bug (`lastInferredSpeedKmh` reset on sub-`MIN_SPEED_INFER_M`
#     stationary samples) seeded via `geo_fix`; iOS has a separate
#     `SpeedInference` with its own unit tests, and `simctl location set` doesn't
#     reproduce the Android FLP cached-last-known cold start. The scenario's own
#     anti-vacuous guard (`assert_signal_observed`) flags the missing diagnostic
#     stream on iOS instead of passing vacuously.
#   - `tts_cold_start_leadin` guards the Android `AudioAlertManager.kt`
#     silent-lead-in fix (audio-focus route warmup over Android Auto /
#     Bluetooth); iOS speaks through AVAudioSession with different activation
#     mechanics and emits no `speak: cold start` line.
_ANDROID_ONLY_EDGE = {"noisy_fix_rejected", "cold_start_spike", "tts_cold_start_leadin"}
HISTORY_SCENARIOS = [
    "retention_roundtrip",
    "records_traversal",
    "retention_none",
]
SYNC_SCENARIOS = [
    "zones_happy",
    # Keep network-dependent scenarios before `zones_offline` — it toggles
    # connectivity and the emulator's DNS can take a few seconds to recover.
    "zones_toggle_off",
    "zones_freshness",
    "zones_remote_older",
    "zones_offline",
    # Map sync is feature-gated off (see FeatureFlags on both platforms).
    # `map_disabled` asserts the gate is in place; restore `map_happy` when
    # the backend lights up.
    "map_disabled",
]


def _load_module_scenarios(package: str, names: list[str]) -> list[Scenario]:
    out: list[Scenario] = []
    for name in names:
        mod = importlib.import_module(f"qa.scenarios.{package}.{name}")
        out.append(mod.build())
    return out


def _location_source_scenario() -> Scenario:
    """The flavor tripwire — asserts the installed build selects the GPS source
    its flavor implies (or, in --flavor auto, just that one was selected)."""
    mod = importlib.import_module("qa.scenarios.location.source_selected")
    return mod.build(EXPECTED_LOCATION_SOURCE)


def _location_source_prefix() -> list[Scenario]:
    """Android-only prefix for smoke/representative. The flavor tripwire asserts
    on the `SrednaBG.LocSrc` line emitted by the flavor-specific `LocationSource`
    factory (`aosp`/`gms`); iOS has a single `CLLocationManager` path and emits
    no such log, so the scenario can never pass there. Skip it on iOS rather than
    fail."""
    if device_mod.current().platform == "ios":
        return []
    return [_location_source_scenario()]


def _smoke_suite() -> list[Scenario]:
    """1 zone, 1 settings combo, single zone sync, parser self-test (last —
    it judges the event-type coverage of the whole suite run).

    Picks `trakiya-01-east` because we have real-fixture coverage in
    core unit tests for that zone — same data path proven good.
    """
    from qa.scenarios.bulk_loader import BulkScenarioSpec, build_scenario as build_bulk

    spec = BulkScenarioSpec(
        name="smoke.trakiya-01-east",
        zone_id="trakiya-01-east",
        speed_kmh=130,
        approach_km=1.5,
        exit_km=0.8,
        compression=4.0,
        settings="S1",
    )
    bulk_one = build_bulk(spec)

    sync_one = importlib.import_module("qa.scenarios.sync.zones_happy").build()
    self_test = importlib.import_module("qa.scenarios.parser_self_test").build()

    return _location_source_prefix() + [bulk_one, sync_one, self_test]


def _representative_suite() -> list[Scenario]:
    return (
        _location_source_prefix()
        + load_representative()
        + _load_module_scenarios("sync", SYNC_SCENARIOS)
    )


def load_representative() -> list[Scenario]:
    """Load the representative-tier matrix: 6 hand-picked zones × 4 settings
    combos = 24 scenarios.

    Prefers the committed YAMLs in `scenarios/representative/` (regenerate with
    `python -m qa.scenarios.representative._generate`). If they're absent (fresh
    checkout before generation), falls back to synthesizing the same 24 from the
    `representative_zones.yaml` fixture × `ALL_COMBOS` — so the suite is never
    silently reduced to a smaller set."""
    if not REPRESENTATIVE_DIR.exists() or not list(REPRESENTATIVE_DIR.glob("*.yaml")):
        import yaml
        from qa import settings as settings_mod
        from qa.scenarios.bulk_loader import BulkScenarioSpec, build_scenario as build_bulk

        fixture_path = _HERE / "fixtures" / "representative_zones.yaml"
        zones = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))["zones"]
        out: list[Scenario] = []
        for z in zones:
            speed = float(z.get("speed_kmh", 130))
            for combo in settings_mod.ALL_COMBOS:
                out.append(build_bulk(BulkScenarioSpec(
                    name=f"rep.{z['id']}__{combo.id}",
                    zone_id=z["id"],
                    speed_kmh=speed,
                    settings=combo.id,
                )))
        return out
    specs = load_specs_from_dir(REPRESENTATIVE_DIR)
    return [build_scenario(s) for s in specs]


def _full_zones_suite() -> list[Scenario]:
    if not BULK_DIR.exists() or not list(BULK_DIR.glob("*.yaml")):
        print("No bulk YAMLs found. Generate first with:", file=sys.stderr)
        print("    python -m qa.scenarios.bulk._generate", file=sys.stderr)
        sys.exit(2)
    specs = load_specs_from_dir(BULK_DIR)
    return [build_scenario(s) for s in specs]


def _edge_suite() -> list[Scenario]:
    names = EDGE_SCENARIOS
    if device_mod.current().platform == "ios":
        names = [n for n in names if n not in _ANDROID_ONLY_EDGE]
    return _load_module_scenarios("edge", names)


def _sync_suite() -> list[Scenario]:
    return _load_module_scenarios("sync", SYNC_SCENARIOS)


def _history_suite() -> list[Scenario]:
    """History-feature scenarios. Cross-platform — they read the history DB via
    the active device's `dump_history()` (Android `DUMP_HISTORY` broadcast, iOS
    `/history?action=dump`), both emitting the same `DUMP_HISTORY …` line parsed
    into a `HistoryDump` event."""
    return _load_module_scenarios("history", HISTORY_SCENARIOS)


def _ui_suite() -> list[Scenario]:
    """UI smoke is a degenerate scenario list — wraps the smoke_walk.

    Android-only: `smoke_walk` drives the phone UI via `adb shell input tap`
    with hardcoded Pixel-8a bottom-nav coordinates (`qa/ui.py`), which has no
    iOS analog (there's no adb device, and the coords are device-specific). Skip
    it on iOS rather than crash — same philosophy as `_location_source_prefix`
    and the `_ANDROID_ONLY_EDGE` skip. A genuine iOS UI walk would route through
    `IosDevice.select_tab` (cf. `srednabg_screenshots.navigate_tab`); a future
    enhancement, not wired here."""
    if device_mod.current().platform == "ios":
        return []
    from qa.scenarios.ui import font_scale_cards, history_show_on_map, smoke_walk_scenario
    return [
        smoke_walk_scenario.build(),
        font_scale_cards.build(),
        history_show_on_map.build(),
    ]


SUITE_BUILDERS = {
    "smoke": _smoke_suite,
    "representative": _representative_suite,
    "full-zones": _full_zones_suite,
    "scenarios": _edge_suite,
    "sync": _sync_suite,
    "history": _history_suite,
    "ui": _ui_suite,
}


def _nightly() -> list[Scenario]:
    out: list[Scenario] = []
    out.extend(_representative_suite())
    out.extend(_full_zones_suite())
    out.extend(_edge_suite())
    out.extend(_history_suite())
    out.extend(_ui_suite())
    return out


SUITE_BUILDERS["nightly"] = _nightly


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", required=True, choices=sorted(SUITE_BUILDERS.keys()))
    p.add_argument("--filter", default=None,
                   help="Substring filter on scenario name (e.g. 'trakiya')")
    p.add_argument("--platform", choices=["auto", "android", "ios"], default="auto",
                   help="Target platform. 'auto' picks whatever's booted; "
                        "iOS requires macOS.")
    p.add_argument("--flavor", choices=["auto", "aosp", "gms"], default="auto",
                   help="Android product flavor under test. 'aosp' asserts the "
                        "app selects the LocationManager source; 'gms' asserts "
                        "FusedLocationProvider; 'auto' (default) only records "
                        "which source was selected. The harness does not build "
                        "or install — install the matching flavor APK first.")
    p.add_argument("--reports-dir", default=None, type=Path,
                   help="Root directory for reports (default: qa/reports). Give "
                        "each platform its own root when running Android and iOS "
                        "concurrently so their <suite>-<timestamp> dirs don't clash.")
    args = p.parse_args(argv)

    reports_root = args.reports_dir or REPORTS_ROOT

    global EXPECTED_LOCATION_SOURCE
    EXPECTED_LOCATION_SOURCE = _FLAVOR_TO_SOURCE[args.flavor]

    # Translate SIGTERM into KeyboardInterrupt so the `with SuiteRunner(...)`
    # block's __exit__ runs and we don't leave the app's foreground service
    # firing TTS announcements after the orchestrator is killed (e.g. by
    # the harness's TaskStop). SIGINT already raises KeyboardInterrupt.
    def _on_term(signum, _frame):
        raise KeyboardInterrupt(f"received signal {signum}")
    signal.signal(signal.SIGTERM, _on_term)

    try:
        d = device_mod.make(args.platform)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    device_mod.set_current(d)

    d.require_device()
    if not d.package_installed():
        kind = "debug APK" if d.platform == "android" else "Debug .app"
        print(f"{d.package_id} not installed on {d.platform}; build + install the {kind} first",
              file=sys.stderr)
        return 2
    d.grant_runtime_permissions()
    d.mute_audio()

    scenarios = SUITE_BUILDERS[args.suite]()
    if args.filter:
        scenarios = [s for s in scenarios if args.filter in s.name]
        if not scenarios:
            print(f"no scenarios matched filter {args.filter!r}", file=sys.stderr)
            return 2

    reports_root.mkdir(parents=True, exist_ok=True)
    print(f"Running suite '{args.suite}' — {len(scenarios)} scenarios")
    runner = None
    try:
        with SuiteRunner(args.suite, reports_root) as runner:
            for sc in scenarios:
                print(f"  · {sc.name} ... ", end="", flush=True)
                r = runner.run(sc)
                print(f"{'PASS' if r.passed else 'FAIL'} ({r.duration_s:.1f}s)")
                if not r.passed:
                    print(f"      {r.failure_message[:200]}")

            junit, md = write_reports(args.suite, runner.report_dir, runner.results)
            print(f"\nReport: {md}")
            print(f"JUnit:  {junit}")
            n_fail = sum(1 for r in runner.results if not r.passed)
            return 0 if n_fail == 0 else 1
    except KeyboardInterrupt:
        print("\nInterrupted — app stopped, foreground service killed.", file=sys.stderr)
        # Don't lose hours of a long run: persist whatever scenarios finished
        # before the interrupt, flagged as a partial report so it isn't mistaken
        # for a full pass. (write_reports only ran post-loop until now.)
        if runner is not None and runner.results:
            junit, md = write_reports(args.suite, runner.report_dir, runner.results,
                                      interrupted=True)
            print(f"Partial report ({len(runner.results)} scenarios): {md}", file=sys.stderr)
            print(f"JUnit:  {junit}", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
