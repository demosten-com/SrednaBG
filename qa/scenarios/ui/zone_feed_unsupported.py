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

Why the scroll needs headroom (a flake this scenario shipped with, nightly run
31987631052). `uiautomator dump` reports only nodes **visible to the user**, and
the notice renders *below* the `settings-zone-data-hash` anchor with the whole
About block (divider, logo, version, license, attribution) below that — so the
list is nowhere near its scroll end when the anchor first appears. Scrolling
until the anchor was merely *present* therefore stopped with the anchor as low
as the last line of the scroll viewport, leaving the notice clipped: the
`present=False` leg passed vacuously, the `present=True` leg failed for the full
poll budget, and each retry re-checked the same un-scrolled position — which is
exactly the observed failure and its 15 s timing. Each swipe moves ~1000 px, so
whether the anchor lands in that ~100 px window is luck, which is why it took
four nights to show up. The swipe now continues until the anchor has
`ANCHOR_HEADROOM_PX` of **scroll viewport** (not display — the Scaffold clips
its content above the bottom nav bar) beneath it, so "absent" means absent
rather than off-screen.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET

from ... import adb
from ... import device as device_mod
from ... import settings, uiauto
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda
from ...ui import UiRecorder

SETTING_KEY = "zone_feed_unsupported"
NOTICE_RESOURCE_ID = "settings-zone-data-unsupported"
HASH_RESOURCE_ID = "settings-zone-data-hash"
POLL_TIMEOUT_S = 15.0
# Scroll viewport that must remain below the anchor row for the notice under it
# to be rendered. Measured on a 1080x2400 Pixel 8a: viewport [63, 2064], anchor
# row 42 px tall, notice 84 px (it wraps to two bodySmall lines). 200 px is
# comfortably over that without demanding more scroll room than the About block
# below it provides.
ANCHOR_HEADROOM_PX = 200


def _scroll_to_zone_data() -> ET.Element:
    """Swipe the Settings list until the zone-data block is on screen *with
    room to spare below the anchor* — see the module docstring.

    Anchored on the hash row rather than on a swipe count: the block sits below
    every toggle, so how far it is depends on screen size and font scale, and a
    fixed number of swipes silently stops working on a different device.
    """
    _, height = uiauto.display_size()
    last_bottom: int | None = None
    last_viewport = height
    for _ in range(8):
        root = uiauto.dump_ui()
        anchor = uiauto.find_by_resource_id(root, HASH_RESOURCE_ID)
        if anchor is not None:
            last_bottom = uiauto.bounds_of(anchor)[3]
            last_viewport = uiauto.scroll_viewport_bottom(root, height)
            if last_bottom <= last_viewport - ANCHOR_HEADROOM_PX:
                return root
        adb.shell("input swipe 540 1600 540 600 300")
        time.sleep(0.8)
    if last_bottom is None:
        raise AssertionFailure(
            f"'{HASH_RESOURCE_ID}' never scrolled into view — is the Settings tab open?")
    raise AssertionFailure(
        f"'{HASH_RESOURCE_ID}' never got {ANCHOR_HEADROOM_PX}px of headroom "
        f"(bottom={last_bottom}, scroll viewport bottom={last_viewport}) — the "
        f"notice below it would be clipped, so its absence would prove nothing")


def _await_notice(ctx: RunContext, *, present: bool) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    root: ET.Element | None = None
    while time.monotonic() < deadline:
        root = _scroll_to_zone_data()
        if uiauto.has_resource_id(root, NOTICE_RESOURCE_ID) == present:
            return
        time.sleep(1.0)
    UiRecorder(ctx.report_dir).screenshot("zone_feed_unsupported_failed")
    anchor = uiauto.find_by_resource_id(root, HASH_RESOURCE_ID) if root is not None else None
    where = (
        f"anchor bounds={uiauto.bounds_of(anchor)}, scroll viewport bottom="
        f"{uiauto.scroll_viewport_bottom(root, uiauto.display_size()[1])}"
        if anchor is not None else "anchor missing"
    )
    raise AssertionFailure(
        f"'{NOTICE_RESOURCE_ID}' was {'absent' if present else 'present'}, "
        f"expected {'present' if present else 'absent'} for "
        f"{SETTING_KEY}={present} ({where})"
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
        uiauto.tap_node(uiauto.dump_ui(), "tab-settings", "Settings tab")
        time.sleep(1.5)
        _await_notice(ctx, present=False)

    def assert_notice_shown(ctx: RunContext) -> None:
        settings.set_setting(SETTING_KEY, True, obs=ctx.obs)
        _await_notice(ctx, present=True)
        UiRecorder(ctx.report_dir).screenshot("zone_feed_unsupported_shown")

    def assert_notice_clears(ctx: RunContext) -> None:
        # A re-supported feed must clear its own notice — see module docstring.
        settings.set_setting(SETTING_KEY, False, obs=ctx.obs)
        _await_notice(ctx, present=False)

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
