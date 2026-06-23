# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Event-stream assertions consumed by `runner.py`.

Each assertion takes a `LogcatObserver`, drains events from its queue,
and either succeeds (returns the matched event for chaining) or raises
`AssertionFailure(message, observer)` so the runner can attach the
recent log lines + a screenshot to the report.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Callable, Optional, Type, TypeVar

from .events import Crash, Event
from .log_observer import LogObserver

T = TypeVar("T", bound=Event)


@dataclass
class AssertionFailure(Exception):
    message: str
    observer: Optional[LogObserver] = None

    def __str__(self) -> str:
        return self.message


def expect(
    obs: LogObserver,
    event_type: Type[T],
    *,
    where: Optional[Callable[[T], bool]] = None,
    within_s: float = 5.0,
    description: str = "",
) -> T:
    """Wait for the next event of `event_type` matching `where`.

    Drains the queue continuously; events that don't match are kept in
    `obs.recent_lines` for context but do not block subsequent
    assertions (they're discarded if not matched here).
    """
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        try:
            ev = obs.queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if isinstance(ev, Crash):
            raise AssertionFailure(f"crash detected during expect({event_type.__name__}): {ev.raw}", obs)
        if isinstance(ev, event_type) and (where is None or where(ev)):
            return ev
    suffix = f" — {description}" if description else ""
    raise AssertionFailure(
        f"timed out after {within_s}s waiting for {event_type.__name__}{suffix}",
        obs,
    )


def expect_in_order(
    obs: LogObserver,
    sequence: list[tuple[Type[Event], Optional[Callable[[Event], bool]]]],
    *,
    within_s: float = 30.0,
    description: str = "",
) -> list[Event]:
    """Match events in the given order. Other intervening events are skipped."""
    out: list[Event] = []
    deadline = time.monotonic() + within_s
    for event_type, predicate in sequence:
        remaining = max(0.5, deadline - time.monotonic())
        ev = expect(obs, event_type, where=predicate, within_s=remaining, description=description)
        out.append(ev)
    return out


def expect_never(
    obs: LogObserver,
    event_type: Type[T],
    *,
    where: Optional[Callable[[T], bool]] = None,
    within_s: float = 5.0,
    description: str = "",
) -> None:
    """Verify an event does NOT occur within the window. Useful for
    'no false re-entry' style assertions during a known-good drive.

    WARNING — lossy: this consumes-and-discards every event it drains
    during the window without re-queueing. Events seen here are gone for
    good, so a *later* `expect(...)` in the same scenario will not see
    them. Use `expect_never` only as the **last** assertion in a scenario
    (all current call sites do). Don't insert an `expect_never` mid-scenario
    expecting subsequent assertions to still observe the drained events.
    """
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        try:
            ev = obs.queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if isinstance(ev, Crash):
            raise AssertionFailure(f"crash detected during expect_never: {ev.raw}", obs)
        if isinstance(ev, event_type) and (where is None or where(ev)):
            suffix = f" — {description}" if description else ""
            raise AssertionFailure(
                f"unexpected {event_type.__name__} occurred: {ev}{suffix}", obs,
            )


def expect_crash_free(obs: LogObserver) -> None:
    """One-shot: snapshot the crash buffer and fail if the app crashed.

    Only fails when the crash mentions the app's package/bundle id. Host-
    side crashes (audio HAL, GPU driver, surfaceflinger on Android;
    simulated-app daemon noise on iOS) are reported into the same buffer
    but are not our bug, and treating them as scenario failures poisons
    an otherwise-green run (see runner.clear_crash_buffer comment about
    "audio-HAL wobble on scenario N failing N+1").
    """
    from . import device as device_mod
    d = device_mod.current()
    buf = d.crash_buffer()
    if not buf.strip():
        return
    if d.package_id not in buf:
        return
    raise AssertionFailure(f"crash buffer non-empty:\n{buf[:2000]}", obs)
