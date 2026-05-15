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
