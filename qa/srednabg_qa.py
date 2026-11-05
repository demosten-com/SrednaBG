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

`--zones live` (the nightly's default) drives the catalog `/api/zones` is
serving instead of the bundled `backend/data/zones.json` — see
`qa/zone_source.py` and `qa/scenarios/live_zones.py`.

Exit code is 0 when all scenarios passed, 1 otherwise. Reports land in
qa/reports/<suite>-<timestamp>/ (junit.xml + summary.md + screenshots/).
"""

from __future__ import annotations

import argparse
import importlib
import json
import signal
import sys
import traceback
from collections.abc import Callable, Iterator
from pathlib import Path

# Allow running both as `python qa/srednabg_qa.py` and `python -m qa.srednabg_qa`
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from qa._preflight import require  # noqa: E402

require("yaml")

from qa import device as device_mod  # noqa: E402
from qa import zone_source, zone_selection  # noqa: E402
from qa.assertions import AssertionFailure  # noqa: E402
from qa.report import write_reports  # noqa: E402
from qa.runner import Scenario, SuiteRunner, step_lambda  # noqa: E402
from qa.scenarios import live_zones  # noqa: E402
from qa.scenarios.bulk_loader import (  # noqa: E402
    BulkScenarioSpec,
    build_scenario,
    load_specs_from_dir,
    specs_for_catalog,
)

REPORTS_ROOT = _HERE / "reports"
BULK_DIR = _HERE / "scenarios" / "bulk"

# Which location source the installed flavor is expected to select, set from
# the --flavor CLI arg before suites are built: "system" (aosp), "fused" (gms),
# or None (auto — record-only, don't pin the flavor). Read by the
# location.source_selected scenario prepended to smoke + representative.
EXPECTED_LOCATION_SOURCE: str | None = None
_FLAVOR_TO_SOURCE = {"aosp": "system", "gms": "fused", "auto": None}
EDGE_DIR = _HERE / "scenarios" / "edge"
SYNC_DIR = _HERE / "scenarios" / "sync"

EDGE_SCENARIOS = [
    "stop_in_zone",
    "gps_dropout",
    "wrong_direction",
    "u_turn",
    "vehicle_swap",
    "vehicle_type_limit_badge",
    "bus_class_limit",
    "over_limit_recovery",
    "off_ramp",
    "cold_start_spike",
    "speed_decay_after_stop",
    "auto_stop",
    "stop_silences_tts",
    "tts_cold_start_leadin",
    "dense_centerline",
    "noisy_fix_rejected",
    "parallel_motorway",
    "mid_zone_join",
    "jog_start_measured",
    "provisional_entry",
    "provisional_entry_abandoned",
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
    # Tripwire on the *served* data, not the client: fails when the backend
    # publishes a zone with no usable geometry (the 2026-08 Път I-8 outage).
    "zones_all_usable",
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


def _build_or_fail(name: str, build: Callable[[], Scenario]) -> Scenario:
    """Keep builder errors in the report instead of losing the suite.

    Only an explicit NotApplicable prerequisite becomes a skip. Missing fields,
    route-generation bugs and unexpected exceptions remain failing scenarios.
    """
    zone_selection.selections.clear()
    try:
        scenario = build()
        if not scenario.zone_ids:
            scenario.zone_ids = tuple(dict.fromkeys(s["zone_id"] for s in zone_selection.selections))
        return scenario
    except zone_selection.NotApplicable as e:
        return Scenario(name=name, steps=[], skip_reason=str(e))
    except Exception as e:
        message = f"could not build scenario: {type(e).__name__}: {e}\n{traceback.format_exc()}"

        def _fail(ctx) -> None:
            raise AssertionFailure(message)

        return Scenario(name=name, steps=[step_lambda("build", _fail)], timeout_s=30)


def _build_specs(specs: list[BulkScenarioSpec], *, category: str = "") -> list[Scenario]:
    scenarios = []
    for spec in specs:
        scenario = _build_or_fail(spec.name, lambda s=spec: build_scenario(s))
        scenario.zone_ids = (spec.zone_id,)
        scenario.category = category
        scenarios.append(scenario)
    return scenarios


def _load_module_scenarios(package: str, names: list[str]) -> list[Scenario]:
    def _build(name: str) -> Scenario:
        return importlib.import_module(f"qa.scenarios.{package}.{name}").build()

    scenarios = [_build_or_fail(f"{package}.{name}", lambda n=name: _build(n)) for name in names]
    for scenario in scenarios:
        scenario.category = package
    return scenarios


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

    Selects a motorway long enough for a useful traversal from the active catalog.
    """
    from qa.scenarios.edge._helpers import DEFAULT_ZONE

    zone_id = zone_selection.select(DEFAULT_ZONE)["id"]
    spec = BulkScenarioSpec(
        name=f"smoke.{zone_id}",
        zone_id=zone_id,
        speed_kmh=130,
        approach_km=1.5,
        exit_km=0.8,
        compression=4.0,
        settings="S1",
    )
    bulk_one = build_scenario(spec)

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
    """Extra S1–S4 coverage selected from the active catalog."""
    from qa.settings import ALL_COMBOS
    specs = []
    for zone in zone_selection.representative_zones():
        for combo in ALL_COMBOS:
            # Stay below this vehicle's current limit; dedicated edge tests
            # own over-limit warning assertions.
            speed = max(10, zone["speed_limits"][combo.vehicle_type] - 10)
            specs.append(BulkScenarioSpec(
                name=f"representative.{zone['id']} [{combo.id}]",
                zone_id=zone["id"], speed_kmh=speed, settings=combo.id))
    return _build_specs(specs, category="representative")


def _full_zones_suite() -> list[Scenario]:
    if zone_source.is_live():
        # The committed YAMLs enumerate the *bundled* catalog; a live run drives
        # every zone actually being served, including ones added since.
        return _build_specs(specs_for_catalog(), category="full-zones")
    if not BULK_DIR.exists() or not list(BULK_DIR.glob("*.yaml")):
        print("No bulk YAMLs found. Generate first with:", file=sys.stderr)
        print("    python -m qa.scenarios.bulk._generate", file=sys.stderr)
        sys.exit(2)
    return _build_specs(load_specs_from_dir(BULK_DIR), category="full-zones")


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
    from qa.scenarios.ui import (
        font_scale_cards,
        history_show_on_map,
        smoke_walk_scenario,
        zone_feed_unsupported,
    )
    return [
        smoke_walk_scenario.build(),
        font_scale_cards.build(),
        history_show_on_map.build(),
        zone_feed_unsupported.build(),
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


def _pin_live_zones(snapshot_path: Path | None = None) -> Iterator[Scenario]:
    """Yield the pin step; whatever is built after it sees the live catalog."""
    zone_source.use_bundled()  # a failed pin must never reuse an earlier snapshot
    yield live_zones.build(snapshot_path)
    if not zone_source.is_live():
        raise _LiveZonesUnavailable


class _LiveZonesUnavailable(Exception):
    """The pin step failed, so there is no catalog to build the rest from."""


def _nightly(live: bool = False, snapshot_path: Path | None = None) -> Iterator[Scenario]:
    """A generator on purpose: scenarios are *built* from the zone catalog, and
    on a live run the catalog only exists once the pin step has run — so every
    drive scenario must be built after it, i.e. lazily, mid-suite.

    The sync scenarios go first: they re-fetch from the server and re-enable the
    periodic sync, both of which the pin step then has the last word on."""
    yield from _location_source_prefix()
    yield from _sync_suite()
    if live:
        yield from _pin_live_zones(snapshot_path)
    # Construct all drives before spending hours running them. An explicit
    # plan makes selection changes and unavailable coverage visible immediately.
    planned = (load_representative() + _full_zones_suite() + _edge_suite()
               + _history_suite() + _ui_suite())

    def save_plan(ctx):
        manifest = [{"name": s.name, "zones": s.zone_ids, "category": s.category,
                     "skip_reason": s.skip_reason} for s in planned]
        (ctx.report_dir / "plan.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n      Planned {len(planned)} scenarios; "
              f"{sum(s.category == 'full-zones' for s in planned)} full-zone traversals")
        for scenario in planned:
            if scenario.skip_reason:
                print(f"      Not applicable: {scenario.name}: {scenario.skip_reason}")

    yield Scenario("zones.plan", [save_plan])
    yield from planned


SUITE_BUILDERS["nightly"] = _nightly


def _live_plan(suite: str, snapshot_path: Path | None = None) -> Iterator[Scenario]:
    """`--zones live`: the suite's scenarios, built after the pin step has run."""
    try:
        if suite == "nightly":
            yield from _nightly(live=True, snapshot_path=snapshot_path)
        else:
            yield from _pin_live_zones(snapshot_path)
            yield from SUITE_BUILDERS[suite]()
    except _LiveZonesUnavailable:
        print("      live zones could not be pinned — the rest of the suite is "
              "built from that catalog and was not run", file=sys.stderr)


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
    p.add_argument("--zones", choices=["auto", "bundled", "live"], default="auto",
                   help="Zone catalog to drive. 'bundled' = backend/data/zones.json. "
                        "'live' = make the device sync /api/zones, download the same "
                        "payload and build every scenario from it. 'auto' (default) "
                        "is live for the nightly suite, bundled for the rest.")
    p.add_argument("--zones-snapshot", type=Path,
                   help="Shared live snapshot; device sync must match its hash")
    args = p.parse_args(argv)
    live = args.zones == "live" or (args.zones == "auto" and args.suite == "nightly")

    if args.zones_snapshot and not live:
        p.error("--zones-snapshot requires --zones live or the nightly suite")
    zone_source.use_bundled()
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

    reports_root.mkdir(parents=True, exist_ok=True)
    scenarios: Iterator[Scenario]
    if live:
        # Lazy: nothing past the pin step can be built until it has run.
        scenarios = _live_plan(args.suite, args.zones_snapshot)
        print(f"Running suite '{args.suite}' against the live zone feed")
    else:
        built = list(SUITE_BUILDERS[args.suite]())
        print(f"Running suite '{args.suite}' — {len(built)} scenarios")
        print(f"Zones under test: {zone_source.describe()}")
        scenarios = iter(built)
    if args.filter:
        # The pin step survives any filter — the scenarios it selects are
        # built from the catalog that step provides.
        scenarios = (s for s in scenarios
                     if args.filter in s.name or s.name in (live_zones.PIN_NAME, "zones.plan"))

    runner = None
    try:
        with SuiteRunner(args.suite, reports_root) as runner:
            try:
                for sc in scenarios:
                    print(f"  · {sc.name} ... ", end="", flush=True)
                    r = runner.run(sc)
                    print(f"{'SKIP' if r.skip_reason else 'PASS' if r.passed else 'FAIL'} ({r.duration_s:.1f}s)")
                    if r.skip_reason:
                        print(f"      {r.skip_reason}")
                    if r.failed:
                        print(f"      {r.failure_message[:200]}")
                    elif sc.name == live_zones.PIN_NAME:
                        print(f"      Zones under test: {zone_source.describe()}")
            finally:
                # Before the runner tears the app down: hand the device back
                # able to sync, whether the suite finished or was interrupted.
                live_zones.release()

            if live and zone_source.is_live() and not args.filter and args.suite in ("nightly", "full-zones"):
                covered = {z for r in runner.results if r.category == "full-zones" and not r.skip_reason
                           for z in r.zone_ids}
                missing = set(zone_source.zones_by_id()) - covered
                if missing:
                    def missing_coverage(ctx):
                        raise AssertionFailure(f"live zones not tested: {', '.join(sorted(missing))}")
                    runner.run(Scenario("zones.coverage", [missing_coverage]))
            ran = [r for r in runner.results if r.name not in (live_zones.PIN_NAME, "zones.plan")]
            if args.filter and not ran:
                print(f"no scenarios matched filter {args.filter!r}", file=sys.stderr)
                return 2
            junit, md = write_reports(args.suite, runner.report_dir, runner.results)
            print(f"\nReport: {md}")
            print(f"JUnit:  {junit}")
            n_fail = sum(1 for r in runner.results if r.failed)
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
