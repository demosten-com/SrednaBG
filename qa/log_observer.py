# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Abstract background log tail.

A LogObserver runs a platform-specific log subprocess in a background
thread, parses each line into a typed `Event` via `qa.parsers`, and pushes
events onto a thread-safe queue.

Test code reads events from `observer.queue` with timeouts; assertion
helpers in `qa.assertions` build on top of this.

Concrete implementations:
  - qa.devices.android_log.AndroidLogObserver (adb logcat -v threadtime)
  - qa.devices.ios_log.IosLogObserver (xcrun simctl spawn booted log stream)

Use `for_current_device()` to get the right observer for the active
Device without the caller hard-coding a platform.
"""

from __future__ import annotations

import queue
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .events import Anr, Crash, Event


@dataclass
class LogObserver:
    """Background log tail — subclassed per platform.

    Subclasses override `_cmd()` (returns the subprocess argv) and
    `_parse(line)` (returns Event | None). They may also override
    `_record_recent` if pre-parse normalization is needed.

    `recent_lines` keeps the last N raw lines for failure-report context.
    """

    queue: "queue.Queue[Event]" = field(default_factory=queue.Queue)
    proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
    thread: Optional[threading.Thread] = None
    recent_lines: list[str] = field(default_factory=list)
    max_recent: int = 400
    _stop: bool = False

    # Subclasses MUST set these on construction.
    package_id: str = ""

    # ── platform hooks (override in subclass) ──────────────────────────────

    def _cmd(self) -> list[str]:
        raise NotImplementedError

    def _parse(self, raw: str) -> Optional[Event]:
        raise NotImplementedError

    def _pre_start(self) -> None:
        """Optional hook for any one-time setup before the subprocess starts
        (e.g. `adb logcat -c` to drop the historical buffer). No-op by default."""

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        self._pre_start()
        self.proc = subprocess.Popen(
            self._cmd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def wait_until_streaming(self, *, timeout_s: float = 8.0) -> bool:
        """Block until the log subprocess is confirmed to be delivering lines.

        Default: no-op (`True`) for backends that attach synchronously or
        backfill a historical buffer — Android's `adb logcat` dumps the ring
        buffer on connect, so a one-shot line is never missed. Overridden by
        backends whose stream attaches asynchronously and drops events emitted
        before attach (iOS's `log stream`)."""
        return True

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        for raw in self.proc.stdout:
            if self._stop:
                break
            raw = raw.rstrip("\n")
            self._record_recent(raw)
            self._maybe_emit_crash(raw)
            ev = self._parse(raw)
            if ev:
                self.queue.put(ev)

    def _record_recent(self, raw: str) -> None:
        self.recent_lines.append(raw)
        if len(self.recent_lines) > self.max_recent:
            del self.recent_lines[0 : len(self.recent_lines) - self.max_recent]

    def _maybe_emit_crash(self, raw: str) -> None:
        # Android: "FATAL EXCEPTION", "ANR in <package>"
        # iOS: simctl log emits "fault" predicate lines containing the bundle id
        if "FATAL EXCEPTION" in raw and self.package_id in raw:
            from .parsers import _now_ms
            self.queue.put(Crash(monotonic_ms=_now_ms(), raw=raw,
                                 process=self.package_id, stack_head=raw))
        elif "ANR in " in raw and self.package_id in raw:
            from .parsers import _now_ms
            self.queue.put(Anr(monotonic_ms=_now_ms(), raw=raw,
                               process=self.package_id, reason=raw))

    def stop(self) -> None:
        self._stop = True
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def drain(self) -> Iterable[Event]:
        """Yield all events currently buffered (non-blocking)."""
        while True:
            try:
                yield self.queue.get_nowait()
            except queue.Empty:
                return

    def clear(self) -> None:
        """Discard buffered events and recent lines. Use before a scenario."""
        list(self.drain())
        self.recent_lines.clear()


def for_current_device() -> LogObserver:
    """Construct the right observer for the active Device."""
    from . import device as device_mod
    d = device_mod.current()
    if d.platform == "android":
        from .devices.android_log import AndroidLogObserver
        return AndroidLogObserver(package_id=d.package_id)
    if d.platform == "ios":
        from .devices.ios_log import IosLogObserver
        return IosLogObserver(package_id=d.package_id)
    raise ValueError(f"no log observer for platform {d.platform!r}")
