# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Home-tab permission cards must keep their action buttons on-screen at a
large accessibility font scale.

Regression trap for a user-reported bug (Samsung A56, large system font):
the NotificationCard's warning text grew until it consumed the whole card
and pushed the "Allow notifications" button below the visible area, so the
permission could not be granted from within the app. The fix pins the
buttons at the card bottom and lets the text scroll
(`HomeScreen.kt` — PermissionCard / NotificationCard / BatteryOptimizationCard).

Mechanism (Android-only, like the rest of the ui suite — uiautomator has no
iOS analog here):
  1. Grant all runtime permissions, then revoke POST_NOTIFICATIONS only, so
     the Home tab lands on NotificationCard — the worst offender (it stacks
     a Button AND a fallback TextButton below the text). The revoke kills
     the app process; we relaunch afterwards.
  2. Pin app_language=en so the asserted button strings are deterministic.
  3. Set system font_scale to 2.0 (the accessibility maximum on stock
     Android) and relaunch.
  4. `uiautomator dump` the accessibility tree and assert both action
     buttons exist and their bounds lie fully within the display. On the
     pre-fix layout the buttons are laid out past the card's clipped bounds
     and either vanish from the dump or report off-screen bounds — both
     fail the assertion.

Teardown always restores font_scale 1.0 and re-grants the permission so
later scenarios/suites are unaffected.
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

# English button labels (res/values-en/strings.xml); app_language is pinned
# to "en" before the check so these are deterministic.
ALLOW_BUTTON_TEXT = "Allow notifications"       # notification_recommended_allow
SETTINGS_BUTTON_TEXT = "Open Settings"          # permission_open_settings

FONT_SCALE_LARGE = "2.0"
POLL_TIMEOUT_S = 20.0


def _dump_ui() -> ET.Element:
    adb.shell("uiautomator dump /sdcard/window_dump.xml")
    raw = subprocess.run(
        [shutil.which("adb"), "exec-out", "cat", "/sdcard/window_dump.xml"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    return ET.fromstring(raw)


def _find_bounds(root: ET.Element, text: str) -> tuple[int, int, int, int] | None:
    for node in root.iter("node"):
        if node.attrib.get("text") != text:
            continue
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds", ""))
        if m:
            return (int(m[1]), int(m[2]), int(m[3]), int(m[4]))
    return None


def _display_size() -> tuple[int, int]:
    out = adb.shell("wm size")
    # Prefer the override size (active resolution) when present.
    sizes = re.findall(r"size:\s*(\d+)x(\d+)", out)
    if not sizes:
        raise AssertionFailure(f"could not parse display size from `wm size`: {out!r}")
    w, h = sizes[-1]
    return int(w), int(h)


def build() -> Scenario:
    def provoke(ctx: RunContext) -> None:
        d = device_mod.current()
        # Location granted + notifications missing => Home shows NotificationCard.
        d.grant_runtime_permissions()
        d.set_setting("app_language", "en")
        adb.shell(f"settings put system font_scale {FONT_SCALE_LARGE}")
        # Revoking a runtime permission kills the app process — relaunch after.
        adb.shell(f"pm revoke {d.package_id} android.permission.POST_NOTIFICATIONS")
        time.sleep(1.0)
        d.start_main()
        time.sleep(3.0)

    def assert_buttons_visible(ctx: RunContext) -> None:
        width, height = _display_size()
        deadline = time.monotonic() + POLL_TIMEOUT_S
        allow = settings_btn = None
        while time.monotonic() < deadline:
            root = _dump_ui()
            allow = _find_bounds(root, ALLOW_BUTTON_TEXT)
            settings_btn = _find_bounds(root, SETTINGS_BUTTON_TEXT)
            if allow and settings_btn:
                break
            time.sleep(1.0)

        UiRecorder(ctx.report_dir).screenshot("font_scale_notification_card")

        for label, bounds in ((ALLOW_BUTTON_TEXT, allow),
                              (SETTINGS_BUTTON_TEXT, settings_btn)):
            if bounds is None:
                raise AssertionFailure(
                    f"button '{label}' not found in the UI at font_scale "
                    f"{FONT_SCALE_LARGE} — pushed off-screen / clipped by the card?")
            left, top, right, bottom = bounds
            if bottom > height or top < 0 or right > width or left < 0:
                raise AssertionFailure(
                    f"button '{label}' is partly off-screen at font_scale "
                    f"{FONT_SCALE_LARGE}: bounds={bounds}, display={width}x{height}")

    def teardown(ctx: RunContext) -> None:
        d = device_mod.current()
        adb.shell("settings put system font_scale 1.0")
        adb.shell(f"pm grant {d.package_id} android.permission.POST_NOTIFICATIONS")
        d.force_stop()
        expect_crash_free(ctx.obs)

    return Scenario(
        name="ui.font_scale_cards",
        steps=[
            step_lambda("provoke_notification_card", provoke),
            step_lambda("assert_buttons_visible", assert_buttons_visible),
        ],
        teardown=teardown,
        timeout_s=90,
    )
