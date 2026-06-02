# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""xcrun simctl spawn booted log stream → typed events.

The iOS app emits structured `os_log` lines under subsystem
`com.demosten.srednabg` with categories that match Android logcat tags:
`SrednaBG.Loc`, `SrednaBG.TTS`, `DebugSync`, `DebugSettings`. The line
body uses the exact same format as Android (e.g.
`onLocation: lat=… lng=… speed=… …`) so the shared `qa.parsers`
regexes work unchanged.

We stream in `--style ndjson` so each event is one JSON object — easier
to split off `category` + `eventMessage` than parsing the human format.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

from qa.devices.ios import BUNDLE_ID
from qa.events import Event
from qa.log_observer import LogObserver
from qa.parsers import parse_message


@dataclass
class IosLogObserver(LogObserver):
    def _cmd(self) -> list[str]:
        # `--info --debug` so we get info-level lines (default is default+).
        # Predicate filters by subsystem so the stream is tractable.
        return [
            "xcrun", "simctl", "spawn", "booted", "log", "stream",
            "--style", "ndjson",
            "--info", "--debug",
            "--predicate", f'subsystem == "{BUNDLE_ID}"',
        ]

    def wait_until_streaming(self, *, timeout_s: float = 8.0, settle_s: float = 0.3) -> bool:
        """`xcrun simctl spawn booted log stream` attaches asynchronously: it
        prints a `Filtering the log data using …` banner once the stream is
        live, then delivers events — but anything logged *before* attach is
        lost (the unified log stream doesn't backfill, unlike `log show`).

        Without this wait the first one-shot event a scenario triggers — e.g.
        the `DebugSync` line in `sync.zones_happy`, the suite's first sync —
        can be emitted into a not-yet-live stream and silently dropped, failing
        only the first sync scenario while later ones pass. A longer timeout
        can't fix that (a missed line stays missed); the stream has to be live
        before the line is logged. Block until the subprocess emits its first
        line (the banner) plus a short settle, so capture is up before the
        first scenario runs. Best-effort: returns False on timeout and the
        caller proceeds — the scenario then surfaces any real failure."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.recent_lines:
                time.sleep(settle_s)
                return True
            time.sleep(0.05)
        return False

    def _parse(self, raw: str) -> Optional[Event]:
        if not raw.strip().startswith("{"):
            return None
        try:
            obj = json.loads(raw)
        except ValueError:
            return None
        category = obj.get("category") or obj.get("subsystem") or ""
        message = obj.get("eventMessage") or obj.get("composedMessage") or ""
        if not category or not message:
            return None
        return parse_message(category, message, raw)
