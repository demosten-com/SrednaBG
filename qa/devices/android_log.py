# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""adb logcat → typed events. Used when the active Device is AndroidDevice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from qa import adb
from qa.events import Event
from qa.log_observer import LogObserver
from qa.parsers import TAGS, parse_threadtime_line


@dataclass
class AndroidLogObserver(LogObserver):
    def _pre_start(self) -> None:
        adb.clear_logcat()

    def _cmd(self) -> list[str]:
        tag_args: list[str] = []
        for t in TAGS:
            tag_args += ["-s", f"{t}:V"]
        return [
            "adb", "logcat", "-v", "threadtime",
            *tag_args,
            "AndroidRuntime:E",  # uncaught Java exceptions
            "ActivityManager:W",  # ANR lines surface here
        ]

    def _parse(self, raw: str) -> Optional[Event]:
        return parse_threadtime_line(raw)
