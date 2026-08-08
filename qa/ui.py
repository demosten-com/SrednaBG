# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""UI helpers: drive the phone UI via the mobile-mcp tools.

This module is consumed in two ways:
  1. The Python orchestrator records WHAT it wants the UI to do
     (a list of `UiCommand`s). It does NOT call mobile-mcp itself —
     that requires the Claude tool harness.
  2. When the harness is run by the /qa-app skill, the skill's Claude
     session reads each pending `UiCommand` from stdout and executes
     it via the mobile-mcp tools.

This separation keeps the Python orchestrator pure-Python (so it works
in CI without an LLM in the loop) while still allowing rich UI smoke
under interactive use.

A simpler fallback path uses `adb shell input tap/keyevent` for
unattended runs — call `tap_via_adb(x, y)` etc. directly.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import device as device_mod


@dataclass
class UiCommand:
    """One UI action the orchestrator wants performed.

    `kind` is one of: tap, screenshot, list_elements, launch_app,
    press_back, expect_text, sleep.
    """
    kind: str
    args: dict = field(default_factory=dict)


class UiRecorder:
    """Records UI commands to a JSONL file under report_dir/ui.jsonl
    and (when adb-only fallback is available) executes them in-process.
    """

    def __init__(self, report_dir: Path):
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.report_dir / "ui.jsonl"
        self.commands: list[UiCommand] = []

    def _emit(self, cmd: UiCommand) -> None:
        self.commands.append(cmd)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": cmd.kind, **cmd.args}) + "\n")

    # ── adb-fallback methods (work without mobile-mcp) ──

    def launch_app(self) -> None:
        d = device_mod.current()
        d.start_main()
        time.sleep(2.0)
        self._emit(UiCommand("launch_app", {"package": d.package_id}))

    def tap_via_adb(self, x: int, y: int) -> None:
        # Android-only fallback. The iOS UI suite drives taps via
        # the harness's mobile-mcp tools, not in-process.
        from . import adb
        adb.shell(f"input tap {x} {y}")
        self._emit(UiCommand("tap", {"x": x, "y": y, "via": "adb"}))

    def press_back(self) -> None:
        from . import adb
        adb.shell("input keyevent 4")
        self._emit(UiCommand("press_back", {}))

    def screenshot(self, name: str) -> Path:
        """Capture via the device's native screenshot path."""
        out = self.report_dir / "screenshots" / f"{name}.png"
        device_mod.current().screencap(out)
        self._emit(UiCommand("screenshot", {"path": str(out)}))
        return out

    # ── mobile-mcp marker methods (no-op in adb-only mode) ──

    def request_mcp_list_elements(self, label: str = "") -> None:
        """Marks a point where the calling Claude session should call
        mcp__mobile-mcp__mobile_list_elements_on_screen and verify the
        expected widgets are present. Recorded in ui.jsonl for replay."""
        self._emit(UiCommand("mcp_list_elements", {"label": label}))


def smoke_walk(report_dir: Path, *, ui: Optional[UiRecorder] = None) -> UiRecorder:
    """Simple unattended UI walk using adb-only commands.

    Launches the app, screenshots Home, taps Settings nav, screenshots,
    taps Map nav, screenshots, taps Home nav, screenshots. Returns the
    recorder so the report writer can list the captured screenshots.

    Coordinates are derived dynamically from `mcp_list_elements`-style
    accessibility tree when available; for the adb-only path we use a
    fallback grid of three nav items at the bottom of a 1080-wide
    portrait screen (Pixel 8a default).
    """
    ui = ui or UiRecorder(report_dir)
    ui.launch_app()
    time.sleep(2.0)
    ui.screenshot("01_home")
    # Bottom nav on 1080×2400 Pixel 8a: Home ≈ x=180, Map ≈ x=540, Settings ≈ x=900, y≈2253
    ui.tap_via_adb(540, 2253)
    time.sleep(1.5)
    ui.screenshot("02_map")
    ui.tap_via_adb(900, 2253)
    time.sleep(1.5)
    ui.screenshot("03_settings")
    ui.tap_via_adb(180, 2253)
    time.sleep(1.5)
    ui.screenshot("04_home_again")
    return ui
