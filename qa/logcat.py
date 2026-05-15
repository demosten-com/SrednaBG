# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Compatibility shim — the real implementation has moved.

Pre-iOS-backend this module owned the regexes (now in `qa.parsers`) and
the adb logcat observer (now `qa.devices.android_log.AndroidLogObserver`,
which is the right pick when the active device is Android).

Existing callers that did `from .logcat import LogcatObserver` keep
working, but new code should use:

    from .log_observer import LogObserver, for_current_device

`for_current_device()` returns the right observer for whichever Device
is active.
"""

from __future__ import annotations

from .log_observer import LogObserver as LogcatObserver  # noqa: F401
from .parsers import (  # noqa: F401
    LINE_RE as _LINE_RE,
    LOC_RE as _LOC_RE,
    DISPLAY_SPEED_RE as _DISPLAY_SPEED_RE,
    STATE_RE as _STATE_RE,
    SPEAK_RE as _SPEAK_RE,
    SPEAK_DROPPED_RE as _SPEAK_DROPPED_RE,
    SUPPRESS_RE as _SUPPRESS_RE,
    ZONES_RE as _ZONES_RE,
    INTERVAL_RE as _INTERVAL_RE,
    SYNC_RE as _SYNC_RE,
    SETTING_RE as _SETTING_RE,
    TAGS,
    parse_threadtime_line as parse_line,
)
