# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""The retired-data-feed notice must appear in Settings, and clear again.

Background. A **data feed** is a served payload variant: feed 1 is `/api/zones`,
feed N>1 is `/api/zones.N`, and a build fetches exactly one of them, chosen at
compile time. When a feed stops being maintained, its `version*.json` grows
`"unsupported": 1`, the client persists that as `zone_feed_unsupported`, and
Settings tells the user their zone data has stopped updating.

Why this scenario has to exist. That flag is the *only* thing the user ever sees
about feeds, it renders from persisted state rather than from a live response,
and no live feed sets it — feed 1 is current and will stay current for a long
time. So the notice is untestable against the real backend, and the way it
breaks is by silently never appearing on the day it finally matters. Hence the
debug key, driving the same `SettingsRepository` setter the sync path uses.

Both directions are asserted. `false` must remove the row, not merely stop
re-adding it: a feed that gets re-supported has to clear its own notice, and a
one-way latch would leave every user permanently told to update.

Android-only, like the rest of the ui suite — it asserts through the uiautomator
accessibility tree. The iOS row carries the same identifier
(`settings-zone-data-unsupported`) for the day that suite grows an iOS analog.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

from ... import adb
from ... import device as device_mod
from ... import settings
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda
from ...ui import UiRecorder

SETTING_KEY = "zone_feed_unsupported"
NOTICE_RESOURCE_ID = "settings-zone-data-unsupported"
HASH_RESOURCE_ID = "settings-zone-data-hash"
POLL_TIMEOUT_S = 15.0


def _dump_ui(timeout_s: float = 10.0) -> ET.Element:
    """uiautomator dump, retried until it yields parseable XML (see
    `history_show_on_map` — the dump is empty while the UI animates)."""
    deadline = time.monotonic() + timeout_s
    while True:
        adb.shell("uiautomator dump /sdcard/window_dump.xml")
        raw = subprocess.run(
            [shutil.which("adb"), "exec-out", "cat", "/sdcard/window_dump.xml"],
            capture_output=True, text=True, check=False, timeout=10,
        ).stdout
        try:
            return ET.fromstring(raw)
        except ET.ParseError:
            if time.monotonic() >= deadline:
                raise AssertionFailure(
                    f"uiautomator dump produced no parseable XML for {timeout_s:.0f}s")
            time.sleep(1.0)


def _has_resource_id(root: ET.Element, resource_id: str) -> bool:
    return any(n.attrib.get("resource-id") == resource_id for n in root.iter("node"))


def _scroll_to_zone_data() -> ET.Element:
    """Swipe the Settings list until the zone-data block is on screen.

    Anchored on the hash row rather than on a swipe count: the block sits below
    every toggle, so how far it is depends on screen size and font scale, and a
    fixed number of swipes silently stops working on a different device.
    """
    for _ in range(8):
        root = _dump_ui()
        if _has_resource_id(root, HASH_RESOURCE_ID):
            return root
        adb.shell("input swipe 540 1600 540 600 300")
        time.sleep(0.8)
    raise AssertionFailure(
        f"'{HASH_RESOURCE_ID}' never scrolled into view — is the Settings tab open?")


def _await_notice(*, present: bool) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        if _has_resource_id(_scroll_to_zone_data(), NOTICE_RESOURCE_ID) == present:
            return
        time.sleep(1.0)
    raise AssertionFailure(
        f"'{NOTICE_RESOURCE_ID}' was {'absent' if present else 'present'}, "
        f"expected {'present' if present else 'absent'} for "
        f"{SETTING_KEY}={present}"
    )


def build() -> Scenario:
    def open_settings(ctx: RunContext) -> None:
        d = device_mod.current()
        d.grant_runtime_permissions()
        # Start from the supported state so "the row appeared" is caused by
        # this run and not left over from an earlier one.
        settings.set_setting(SETTING_KEY, False, obs=ctx.obs)
        d.start_main()
        time.sleep(2.0)
        root = _dump_ui()
        node = next(
            (n for n in root.iter("node") if n.attrib.get("resource-id") == "tab-settings"),
            None,
        )
        if node is None:
            raise AssertionFailure("Settings tab (resource-id 'tab-settings') not found")
        bounds = node.attrib.get("bounds", "")
        left, top, right, bottom = (
            int(v) for v in bounds.replace("][", ",").strip("[]").split(",")
        )
        adb.shell(f"input tap {(left + right) // 2} {(top + bottom) // 2}")
        time.sleep(1.5)
        _await_notice(present=False)

    def assert_notice_shown(ctx: RunContext) -> None:
        settings.set_setting(SETTING_KEY, True, obs=ctx.obs)
        _await_notice(present=True)
        UiRecorder(ctx.report_dir).screenshot("zone_feed_unsupported_shown")

    def assert_notice_clears(ctx: RunContext) -> None:
        # A re-supported feed must clear its own notice — see module docstring.
        settings.set_setting(SETTING_KEY, False, obs=ctx.obs)
        _await_notice(present=False)

    def teardown(ctx: RunContext) -> None:
        settings.set_setting(SETTING_KEY, False)  # belt + suspenders
        device_mod.current().force_stop()
        expect_crash_free(ctx.obs)

    return Scenario(
        name="ui.zone_feed_unsupported",
        steps=[
            step_lambda("open_settings", open_settings),
            step_lambda("assert_notice_shown", assert_notice_shown),
            step_lambda("assert_notice_clears", assert_notice_clears),
        ],
        teardown=teardown,
        timeout_s=120,
    )
