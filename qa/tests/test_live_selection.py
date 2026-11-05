# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
"""Catalog churn must change test inputs, never erase mandatory live coverage."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

import _paths  # noqa: F401
from qa import zone_source, zone_selection
from qa.report import _render_junit, _render_markdown, write_reports
from qa.runner import Scenario, ScenarioResult, SuiteRunner
from qa.scenarios import live_zones
from qa.scenarios.bulk_loader import specs_for_catalog, build_scenario, BulkScenarioSpec, _ensure_gpx
from qa.events import ZoneStateChange
from qa.assertions import AssertionFailure
from qa.srednabg_qa import _build_or_fail, load_representative

ROOT = Path(__file__).resolve().parents[2]


class LiveCatalogTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(zone_source.use_bundled)
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.payload = json.loads((ROOT / 'backend/data/zones.json').read_text())
        self.enterContext(patch.object(zone_source, 'GPX_FIXTURES_DIR', self.tmp / 'gpx'))

    def activate(self, zones):
        payload = {**self.payload, 'zones': zones}
        path = self.tmp / 'snapshot.json'
        path.write_text(json.dumps(payload))
        zone_source._zones_cache.clear()
        zone_source.use_snapshot(zone_source.read_snapshot(path))

    def test_removal_renumbering_and_addition_keep_every_live_zone(self):
        zones = copy.deepcopy(self.payload['zones'])
        # Reproduce the missing I-2 and Kocherinovo inputs, then renumber
        # everything. No role may depend on the remaining familiar ids.
        zones = [z for z in zones if not z['id'].startswith(('i2-', 'i1-02'))]
        for i, z in enumerate(zones):
            z['id'] = f'renumbered-{i}'
        added = copy.deepcopy(zones[0])
        added['id'] = 'new-section'
        zones.append(added)
        self.activate(zones)
        self.assertEqual({s.zone_id for s in specs_for_catalog()}, {z['id'] for z in zones})
        representative = load_representative()
        self.assertEqual(len(representative), 24)
        self.assertTrue(all(not s.skip_reason for s in representative))
        self.assertEqual(len({s.zone_ids[0] for s in representative}), 6)
        for role in ('long_drive', 'wrong_direction', 'silent_join', 'isolated_entry', 'truck_limits', 'bus_limits',
                     'dense_centerline', 'history', 'vehicle_swap'):
            self.assertIn(zone_selection.select(role)['id'], {z['id'] for z in zones})

    def test_selection_is_deterministic_and_road_type_is_optional(self):
        zones = copy.deepcopy(self.payload['zones'])
        self.activate(zones)
        expected = [z['id'] for z in zone_selection.representative_zones()]
        self.activate(list(reversed(zones)))
        self.assertEqual([z['id'] for z in zone_selection.representative_zones()], expected)
        for z in zones:
            z.pop('road_type', None)
        self.activate(zones)
        self.assertEqual(len(zone_selection.representative_zones()), 6)
        self.assertTrue(zone_selection.select('long_drive')['road'].startswith('АМ '))

    def test_missing_vehicle_limit_difference_is_a_skip_not_a_pass(self):
        zones = copy.deepcopy(self.payload['zones'])
        for z in zones:
            z['speed_limits'].update(truck=z['speed_limits']['car'], bus=z['speed_limits']['car'])
        self.activate(zones)
        for role in ('truck_limits', 'bus_limits', 'vehicle_swap'):
            with self.subTest(role=role), self.assertRaises(zone_selection.NotApplicable):
                zone_selection.select(role)
        self.assertEqual(len(specs_for_catalog()), len(zones))

    def test_changed_limits_drive_vehicle_assertions_from_catalog(self):
        zones = copy.deepcopy(self.payload['zones'])
        for z in zones:
            z['speed_limits'].update(car=110, truck=70, bus=80)
        self.activate(zones)
        from qa.scenarios.edge import bus_class_limit
        with patch.object(bus_class_limit, '_build_fixes', return_value=[]) as fixes:
            scenario = bus_class_limit.build()
        self.assertEqual(fixes.call_args.args[1], 95 / 3.6)
        self.assertIn(scenario.zone_ids[0], zone_source.zones_by_id())

    def test_split_long_zones_is_explicit_not_applicable(self):
        zones = copy.deepcopy(self.payload['zones'][:2])
        for z in zones:
            z['centerline'] = z['centerline'][:8]
        self.activate(zones)
        scenario = _build_or_fail('long', lambda: zone_selection.select('long_drive'))
        self.assertIn('long_drive', scenario.skip_reason)
        # Even unsuitable edge inputs remain required full-zone traversals.
        self.assertEqual(len(specs_for_catalog()), 2)

    def test_missing_parallel_road_is_skipped_but_bundled_reproducer_builds(self):
        from qa.scenarios.edge import parallel_motorway
        self.activate(self.payload['zones'])
        self.assertFalse(_build_or_fail('parallel', parallel_motorway.build).skip_reason)
        self.activate([z for z in self.payload['zones'] if not z['id'].startswith('i1-02')])
        result = _build_or_fail('parallel', parallel_motorway.build)
        self.assertIn('absent', result.skip_reason)

    def test_malformed_or_duplicate_zone_is_failure_not_missing_coverage(self):
        for mutate in (lambda zs: zs.append(copy.deepcopy(zs[0])),
                       lambda zs: zs[0].update(centerline=[]),
                       lambda zs: zs[0]['speed_limits'].update(car=0)):
            zones = copy.deepcopy(self.payload['zones'][:2])
            mutate(zones)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.activate(zones)
        scenario = _build_or_fail('broken', lambda: (_ for _ in ()).throw(KeyError('bad field')))
        self.assertFalse(scenario.skip_reason)
        with self.assertRaises(AssertionFailure):
            scenario.steps[0](None)

    def test_concurrent_platform_route_variants_do_not_evict_each_other(self):
        self.activate(self.payload['zones'])
        zid = self.payload['zones'][0]['id']
        normal = _ensure_gpx(BulkScenarioSpec('normal', zid, exit_km=1))
        uturn = _ensure_gpx(BulkScenarioSpec('uturn', zid, exit_km=2))
        self.assertNotEqual(normal, uturn)
        self.assertTrue(normal.exists())
        self.assertTrue(uturn.exists())

    def test_reversed_centerline_remains_start_first(self):
        zone = copy.deepcopy(self.payload['zones'][0])
        normal = copy.deepcopy(zone_selection.centerline(zone))
        zone['centerline'].reverse()
        self.assertEqual(zone_selection.centerline(zone), normal)

    def test_silent_join_rejects_a_tail_that_reverses_at_the_exit_camera(self):
        zone = {'id': 'tail', 'start': {'lat': 42, 'lng': 25},
                'end': {'lat': 42.01, 'lng': 25},
                'centerline': [[42, 25], [42.005, 25], [42.01, 25]]}
        self.assertTrue(zone_selection.exit_clear(zone, {'tail': zone}))
        zone['centerline'].insert(-1, [42.0101, 25])
        self.assertFalse(zone_selection.exit_clear(zone, {'tail': zone}))

    def test_shared_snapshot_change_fails_before_device_sync(self):
        self.activate(self.payload['zones'])
        scenario = live_zones.build(self.tmp / 'snapshot.json')
        ctx = Mock(report_dir=self.tmp / 'report')
        with patch('qa.scenarios.live_zones.device_mod.current'), \
                patch('qa.scenarios.live_zones.time.sleep'), \
                patch.object(zone_source, 'fetch_version', return_value={'hash': 'changed'}), \
                patch('qa.scenarios.live_zones.sync.force_sync_zones') as sync:
            with self.assertRaisesRegex(AssertionFailure, 'changed after the shared snapshot'):
                scenario.steps[0](ctx)
            sync.assert_not_called()

    def test_shared_snapshot_pin_freezes_the_exact_captured_payload(self):
        from qa.runner import RunContext
        self.activate(self.payload['zones'])
        shared = self.tmp / 'snapshot.json'
        expected_bytes = shared.read_bytes()
        ctx = RunContext(Mock(), self.tmp / 'report')
        self.addCleanup(setattr, live_zones, '_frozen', False)
        with patch('qa.scenarios.live_zones.device_mod.current'), \
                patch('qa.scenarios.live_zones.time.sleep'), \
                patch.object(zone_source, 'fetch_version', return_value={'hash': self.payload['hash']}), \
                patch.object(zone_source, '_get_json', return_value=self.payload), \
                patch('qa.scenarios.live_zones.sync.force_sync_zones'), \
                patch('qa.scenarios.live_zones.sync.wait_for_sync', return_value=Mock(outcome='Updated')), \
                patch('qa.scenarios.live_zones.settings.set_setting') as settings:
            live_zones.build(shared).steps[0](ctx)
        self.assertEqual((ctx.report_dir / 'zones-live.json').read_bytes(), expected_bytes)
        self.assertEqual(zone_source.path(), ctx.report_dir / 'zones-live.json')
        self.assertTrue(live_zones._frozen)
        self.assertIn(('zone_sync_enabled', False), [c.args for c in settings.call_args_list])
        self.assertIn(('cached_zone_version', live_zones._FROZEN_VERSION),
                      [c.args for c in settings.call_args_list])

    def test_coverage_report_lists_all_served_ids_and_actual_results(self):
        zones = self.payload['zones'][:2]
        self.activate(zones)
        results = [ScenarioResult('first', True, 1, zone_ids=(zones[0]['id'],), category='full-zones')]
        write_reports('nightly', self.tmp, results)
        coverage = json.loads((self.tmp / 'coverage.json').read_text())
        self.assertEqual(coverage['unattempted_zone_ids'], [zones[1]['id']])
        self.assertEqual(coverage['passed_zone_ids'], [zones[0]['id']])


class SkipAccountingTests(unittest.TestCase):
    def test_skip_never_becomes_a_pass_or_failure_or_runs_device_hooks(self):
        runner = SuiteRunner.__new__(SuiteRunner)
        runner.results = []
        forbidden = Mock(side_effect=AssertionError('must not run'))
        scenario = Scenario('absent', [forbidden], setup=forbidden, teardown=forbidden,
                            skip_reason='no suitable "road"')
        result = runner.run(scenario)
        self.assertFalse(result.passed)
        self.assertFalse(result.failed)
        forbidden.assert_not_called()
        root = ET.fromstring(_render_junit('nightly', [result]))
        self.assertEqual(root.attrib['skipped'], '1')
        self.assertEqual(root.attrib['failures'], '0')
        self.assertIsNotNone(root.find('testcase/skipped'))
        md = _render_markdown('nightly', [result])
        self.assertIn('**0 passed** / **0 failed** / **1 skipped**', md)
        self.assertIn('Unavailable live coverage', md)


class TargetZoneCoverageTests(unittest.TestCase):
    def test_neighbour_traversal_cannot_pass_target_and_handover_can(self):
        plan = Mock(duration_ms=1000)
        plan.compressed.return_value = plan
        with patch('qa.scenarios.bulk_loader._ensure_gpx'), \
                patch('qa.scenarios.bulk_loader.parse_gpx', return_value=plan):
            scenario = build_scenario(BulkScenarioSpec('target', 'target'))
        def events(zone, prev='Outside'):
            return [ZoneStateChange(0, '', prev, 'InZone', zone, None),
                    ZoneStateChange(1, '', 'InZone', 'Exiting', zone, None)]
        ctx = Mock()
        with patch('qa.scenarios.bulk_loader._drain_buffered', return_value=events('neighbour')):
            with self.assertRaisesRegex(AssertionFailure, 'no zone entry observed for target'):
                scenario.steps[-1](ctx)
        with patch('qa.scenarios.bulk_loader._drain_buffered', return_value=events('target', 'Exiting')):
            scenario.steps[-1](ctx)


if __name__ == '__main__':
    unittest.main()
