# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Unit tests for qa/sync.py wait helpers.

Regression for the Jul 2026 nightly flake: `zones_remote_older`'s teardown
fired a restore-sync without consuming its result, and its `UpToDate` event
landed *after* `zones_offline` cleared the buffer — `wait_for_sync` then
returned the stale event as the offline sync's answer. `wait_for_sync_outcome`
must skip past stale non-matching results and still fail loudly (naming what
it saw) when the wanted outcome never arrives.
"""

import queue
import unittest

import _paths  # noqa: F401

from qa import sync
from qa.events import SyncResult


class _StubObs:
    """The wait helpers only touch `.queue`."""

    def __init__(self, events):
        self.queue = queue.Queue()
        for ev in events:
            self.queue.put(ev)


def _res(outcome, action="SYNC_ZONES", detail=""):
    return SyncResult(monotonic_ms=0, raw="", action=action, outcome=outcome, detail=detail)


class WaitForSyncOutcomeTest(unittest.TestCase):
    def test_skips_stale_result_before_match(self):
        obs = _StubObs([_res("UpToDate"), _res("Failed", detail="offline")])
        ev = sync.wait_for_sync_outcome(obs, "SYNC_ZONES", "Failed", timeout_s=2)
        self.assertEqual(ev.outcome, "Failed")
        self.assertEqual(ev.detail, "offline")

    def test_ignores_other_actions(self):
        obs = _StubObs([_res("Skipped", action="SYNC_MAP"), _res("Failed")])
        ev = sync.wait_for_sync_outcome(obs, "SYNC_ZONES", "Failed", timeout_s=2)
        self.assertEqual(ev.outcome, "Failed")

    def test_timeout_names_observed_outcomes(self):
        obs = _StubObs([_res("UpToDate"), _res("Updated", detail="42 zones")])
        with self.assertRaises(TimeoutError) as cm:
            sync.wait_for_sync_outcome(obs, "SYNC_ZONES", "Failed", timeout_s=0.1)
        msg = str(cm.exception)
        self.assertIn("UpToDate", msg)
        self.assertIn("Updated(42 zones)", msg)

    def test_timeout_with_no_events(self):
        obs = _StubObs([])
        with self.assertRaises(TimeoutError) as cm:
            sync.wait_for_sync_outcome(obs, "SYNC_ZONES", "Failed", timeout_s=0.1)
        self.assertIn("nothing", str(cm.exception))


class WaitForSyncTest(unittest.TestCase):
    def test_returns_first_matching_action(self):
        obs = _StubObs([_res("UpToDate"), _res("Failed")])
        ev = sync.wait_for_sync(obs, "SYNC_ZONES", timeout_s=2)
        self.assertEqual(ev.outcome, "UpToDate")


if __name__ == "__main__":
    unittest.main()
