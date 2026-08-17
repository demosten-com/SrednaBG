# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Shared uiautomator accessibility-tree helpers (Android-only).

The `ui` suite asserts through `uiautomator dump` rather than a Compose test
rule, and every scenario in it needs the same four primitives: dump the tree,
find a node by resource-id, read its bounds, and know how big the display is.
They used to be copy-pasted per scenario, which is how one copy could drift
(see `scenarios/ui/zone_feed_unsupported.py` — the dump only reports nodes
*visible to the user*, a property each copy had to rediscover).

iOS has no analog: `IosDevice` drives the app through the loopback debug
listener, so these helpers are only ever called from Android-gated scenarios.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

from . import adb
from .assertions import AssertionFailure

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def dump_ui(timeout_s: float = 10.0) -> ET.Element:
    """`uiautomator dump`, retried until it yields parseable XML.

    The dump intermittently produces nothing while the UI is animating (seen on
    API 36 right after a relaunch); a single failed attempt must not abort the
    scenario.

    Note the tree contains only nodes **visible to the user** — a row that is
    composed but scrolled below the fold is simply absent, indistinguishable
    from one that was never rendered. Scenarios asserting "row X is absent"
    must therefore first prove X's region is on-screen.
    """
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


def find_by_resource_id(root: ET.Element, resource_id: str) -> ET.Element | None:
    for node in root.iter("node"):
        if node.attrib.get("resource-id") == resource_id:
            return node
    return None


def has_resource_id(root: ET.Element, resource_id: str) -> bool:
    return find_by_resource_id(root, resource_id) is not None


def find_by_text(root: ET.Element, text: str) -> ET.Element | None:
    for node in root.iter("node"):
        if node.attrib.get("text") == text:
            return node
    return None


def bounds_of(node: ET.Element) -> tuple[int, int, int, int]:
    """`(left, top, right, bottom)` from the node's `bounds` attribute."""
    m = _BOUNDS_RE.match(node.attrib.get("bounds", ""))
    if not m:
        raise AssertionFailure(f"node has unparseable bounds: {node.attrib.get('bounds')!r}")
    left, top, right, bottom = (int(g) for g in m.groups())
    return left, top, right, bottom


def bounds_center(node: ET.Element) -> tuple[int, int]:
    left, top, right, bottom = bounds_of(node)
    return (left + right) // 2, (top + bottom) // 2


def tap_node(root: ET.Element, resource_id: str, what: str) -> None:
    node = find_by_resource_id(root, resource_id)
    if node is None:
        raise AssertionFailure(f"{what} (resource-id {resource_id!r}) not found in the UI")
    x, y = bounds_center(node)
    adb.shell(f"input tap {x} {y}")


def scroll_viewport_bottom(root: ET.Element, default: int) -> int:
    """Bottom edge (px) of the first scrollable container in the tree.

    Not the same as the display height: the phone UI's Scaffold clips its
    scrolling content above the bottom navigation bar (measured [63, 2064] on a
    1080x2400 Pixel 8a, with the nav bar at 2127-2337), so a row parked between
    the two is never rendered and never appears in the dump. Anything reasoning
    about "is there room below this row" must use this, not `display_size()`.
    """
    for node in root.iter("node"):
        if node.attrib.get("scrollable") == "true":
            return bounds_of(node)[3]
    return default


def display_size() -> tuple[int, int]:
    """Active display size in px, preferring the override (current) resolution."""
    out = adb.shell("wm size")
    sizes = re.findall(r"size:\s*(\d+)x(\d+)", out)
    if not sizes:
        raise AssertionFailure(f"could not parse display size from `wm size`: {out!r}")
    w, h = sizes[-1]
    return int(w), int(h)
