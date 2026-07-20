# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""History detail's "Show on map" action must gate on tracking.

The button (testTag `history-show-on-map`, a TopAppBar action on the History
detail screen) highlights the traversed zone on the Map tab. Two features must
never drive the map at once, so it has to be:

  1. enabled while tracking is off (record loaded, zone resolves), and
  2. disabled the moment tracking starts (`LocationTrackingService` also
     clears any active highlight via `MapHighlightStore` on start).

Mechanism (Android-only, like the rest of the ui suite — asserts through the
uiautomator accessibility tree; iOS has no analog here):
  1. `SEED_HISTORY` fills the DB with the deterministic seeder set, so the
     History list has rows without driving a zone.
  2. Navigate History tab → first record row → detail.
  3. Assert `history-show-on-map` is present and enabled="true".
  4. `START_TRACKING`, re-dump, assert enabled="false".

Teardown stops tracking so later scenarios/suites are unaffected.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

from ... import adb
from ... import device as device_mod
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda
from ...ui import UiRecorder

ACTION_SEED_HISTORY = "com.demosten.srednabg.debug.SEED_HISTORY"
BUTTON_RESOURCE_ID = "history-show-on-map"
ROW_RESOURCE_ID = "history-row"
POLL_TIMEOUT_S = 20.0


def _dump_ui() -> ET.Element:
    adb.shell("uiautomator dump /sdcard/window_dump.xml")
    raw = subprocess.run(
        [shutil.which("adb"), "exec-out", "cat", "/sdcard/window_dump.xml"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    return ET.fromstring(raw)


def _find_by_resource_id(root: ET.Element, resource_id: str) -> ET.Element | None:
    for node in root.iter("node"):
        if node.attrib.get("resource-id") == resource_id:
            return node
    return None


def _bounds_center(node: ET.Element) -> tuple[int, int]:
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds", ""))
    if not m:
        raise AssertionFailure(f"node has unparseable bounds: {node.attrib.get('bounds')!r}")
    left, top, right, bottom = (int(g) for g in m.groups())
    return (left + right) // 2, (top + bottom) // 2


def _tap_node(root: ET.Element, resource_id: str, what: str) -> None:
    node = _find_by_resource_id(root, resource_id)
    if node is None:
        raise AssertionFailure(f"{what} (resource-id {resource_id!r}) not found in the UI")
    x, y = _bounds_center(node)
    adb.shell(f"input tap {x} {y}")


def _await_button(*, enabled: str) -> None:
    """Poll the accessibility tree until the button reports the wanted state."""
    deadline = time.monotonic() + POLL_TIMEOUT_S
    last_seen: str | None = None
    while time.monotonic() < deadline:
        node = _find_by_resource_id(_dump_ui(), BUTTON_RESOURCE_ID)
        if node is not None:
            last_seen = node.attrib.get("enabled")
            if last_seen == enabled:
                return
        time.sleep(1.0)
    if last_seen is None:
        raise AssertionFailure(
            f"'{BUTTON_RESOURCE_ID}' never appeared — is the History detail "
            "screen open and the action present in the TopAppBar?")
    raise AssertionFailure(
        f"'{BUTTON_RESOURCE_ID}' stayed enabled={last_seen!r}, wanted {enabled!r}")


def build() -> Scenario:
    def open_detail(ctx: RunContext) -> None:
        d = device_mod.current()
        d.grant_runtime_permissions()
        # A leftover tracking session from an earlier scenario would flip the
        # gate under test; make the baseline deterministic.
        d.stop_tracking()
        d.start_main()
        time.sleep(2.0)
        adb.broadcast(ACTION_SEED_HISTORY, adb.DEBUG_CONTROL_RECEIVER)
        time.sleep(1.5)
        _tap_node(_dump_ui(), "tab-history", "History tab")
        time.sleep(1.5)
        # Rows carry the `history-row` test tag (matching by display text broke
        # when the translatable caption was reworded); the first tagged node is
        # the newest record's row, so tapping it opens that record's detail.
        # Poll a little — the seeded rows land via a Room Flow emission.
        deadline = time.monotonic() + 10.0
        row = None
        while row is None and time.monotonic() < deadline:
            row = _find_by_resource_id(_dump_ui(), ROW_RESOURCE_ID)
            if row is None:
                time.sleep(1.0)
        if row is None:
            raise AssertionFailure("no history rows visible after SEED_HISTORY")
        x, y = _bounds_center(row)
        adb.shell(f"input tap {x} {y}")
        time.sleep(1.5)

    def assert_enabled_when_idle(ctx: RunContext) -> None:
        _await_button(enabled="true")
        UiRecorder(ctx.report_dir).screenshot("history_show_on_map_enabled")

    def assert_disabled_while_tracking(ctx: RunContext) -> None:
        device_mod.current().start_tracking()
        _await_button(enabled="false")
        UiRecorder(ctx.report_dir).screenshot("history_show_on_map_disabled")

    def teardown(ctx: RunContext) -> None:
        d = device_mod.current()
        d.stop_tracking()
        d.force_stop()
        expect_crash_free(ctx.obs)

    return Scenario(
        name="ui.history_show_on_map",
        steps=[
            step_lambda("open_history_detail", open_detail),
            step_lambda("assert_enabled_when_idle", assert_enabled_when_idle),
            step_lambda("assert_disabled_while_tracking", assert_disabled_while_tracking),
        ],
        teardown=teardown,
        timeout_s=120,
    )
