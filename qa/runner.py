# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Scenario executor.

A `Scenario` is a sequence of `Step`s plus pre/post hooks. The runner
maintains one shared `LogcatObserver` per suite (so we don't lose the
crash buffer between scenarios), but clears its event queue and
recent_lines slice between scenarios.

Each step is a callable taking a `RunContext`. Steps can return data
the next step needs by stashing it on `ctx.data` (keyed by string),
which is also how `assert_event` chains conditional logic.

A scenario terminates as soon as a step raises `AssertionFailure`; the
runner records the failure (with screenshot + last logs) and moves on
to the next scenario rather than aborting the whole suite.
"""

from __future__ import annotations

import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional

from . import device as device_mod
from .assertions import AssertionFailure, expect_crash_free
from .drive import DrivePlan, pump
from .log_observer import LogObserver, for_current_device

Step = Callable[["RunContext"], None]


@dataclass
class RunContext:
    """Lifetime: one Scenario. Steps read/write `data`; the runner sets
    `obs`, `report_dir`, `tts_phrases`."""

    obs: LogObserver
    report_dir: Path
    tts_phrases: dict[str, str] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    name: str
    steps: list[Step]
    setup: Optional[Step] = None
    teardown: Optional[Step] = None
    timeout_s: float = 300.0


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    duration_s: float
    failure_message: str = ""
    failure_step: int = -1
    recent_logs: list[str] = field(default_factory=list)
    screenshot_path: Optional[Path] = None


class SuiteRunner:
    """Owns the observer + report dir for a whole suite of scenarios."""

    def __init__(self, suite_name: str, report_root: Path, *, tts_phrases: Optional[dict[str, str]] = None):
        self.suite_name = suite_name
        self.report_dir = report_root / time.strftime(f"{suite_name}-%Y%m%d-%H%M%S")
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.obs = for_current_device()
        self.tts_phrases = tts_phrases or {}
        self.results: list[ScenarioResult] = []

    def __enter__(self) -> "SuiteRunner":
        device_mod.current().require_device()
        self.obs.start()
        # Block until the log stream is actually capturing before the first
        # scenario fires. iOS's `log stream` attaches asynchronously and drops
        # events logged before attach — without this the suite's first sync
        # (sync.zones_happy) can miss its one-shot DebugSync line. No-op on
        # Android (logcat backfills). See LogObserver.wait_until_streaming.
        self.obs.wait_until_streaming()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.obs.stop()
        # Best-effort cleanup so a killed orchestrator (Ctrl+C, TaskStop,
        # SIGTERM) doesn't leave the foreground LocationTrackingService
        # firing periodic TTS updates from a stale zone state. Wrapped
        # individually so one adb hiccup doesn't skip the rest.
        try:
            from . import settings as qa_settings
            qa_settings.stop_tracking()
        except Exception:
            pass
        try:
            device_mod.current().force_stop()
        except Exception:
            pass

    def run(self, scenario: Scenario) -> ScenarioResult:
        # Fresh slice of events for this scenario.
        self.obs.clear()
        # Clear the crash buffer so `expect_crash_free` in teardown only sees
        # crashes that happened during THIS scenario. Otherwise an emulator-side
        # audio-HAL wobble on scenario N would fail scenarios N+1, N+2, …
        device_mod.current().clear_crash_buffer()
        ctx = RunContext(obs=self.obs, report_dir=self.report_dir, tts_phrases=self.tts_phrases)
        t0 = time.monotonic()
        failure_msg = ""
        failure_step = -1
        try:
            if scenario.setup:
                scenario.setup(ctx)
            for i, step in enumerate(scenario.steps):
                step(ctx)
        except AssertionFailure as af:
            failure_msg = str(af)
            failure_step = i if "i" in dir() else -1  # type: ignore[name-defined]
        except Exception as e:
            failure_msg = f"unexpected {type(e).__name__}: {e}\n{traceback.format_exc()}"
            failure_step = i if "i" in dir() else -1  # type: ignore[name-defined]
        finally:
            try:
                if scenario.teardown:
                    scenario.teardown(ctx)
            except Exception as e:
                if not failure_msg:
                    failure_msg = f"teardown failed: {e}"
        passed = not failure_msg
        result = ScenarioResult(
            name=scenario.name,
            passed=passed,
            duration_s=time.monotonic() - t0,
            failure_message=failure_msg,
            failure_step=failure_step,
            recent_logs=list(self.obs.recent_lines[-200:]),
        )
        self.results.append(result)
        return result


# ─────────────────────────── reusable step factories ───────────────────────────


def step_drive(plan: DrivePlan, *, compression: float = 1.0) -> Step:
    """Pump a DrivePlan via `adb emu geo fix`. Blocks until plan ends."""
    actual = plan.compressed(compression)

    def _do(ctx: RunContext) -> None:
        pump(actual)

    _do.__name__ = f"drive({actual.name})"
    return _do


def step_wait(seconds: float) -> Step:
    def _do(ctx: RunContext) -> None:
        time.sleep(seconds)

    _do.__name__ = f"wait({seconds}s)"
    return _do


def step_lambda(name: str, fn: Callable[[RunContext], None]) -> Step:
    fn.__name__ = name
    return fn


@contextmanager
def with_app_running() -> Iterator[None]:
    """Ensure the app is foregrounded before the block. Caller is responsible
    for tapping Start Tracking via UI helper if needed."""
    d = device_mod.current()
    if not d.app_running():
        d.start_main()
        time.sleep(2.0)
    yield
