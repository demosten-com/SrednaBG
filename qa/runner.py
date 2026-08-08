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

import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from . import device as device_mod
from . import drive as drive_mod
from .assertions import AssertionFailure
from .drive import DrivePlan, DriveAborted, pump
from .log_observer import LogObserver, for_current_device

Step = Callable[["RunContext"], None]


@dataclass
class RunContext:
    """Lifetime: one Scenario. Steps read/write `data`; the runner sets
    `obs`, `report_dir`."""

    obs: LogObserver
    report_dir: Path
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
    # True when the scenario died on an *unexpected* exception (a crash in the
    # harness/app), as opposed to an AssertionFailure or a timeout. Reported as
    # a JUnit <error> rather than a <failure> so suite health distinguishes
    # "assertion didn't hold" from "something blew up".
    errored: bool = False


class SuiteRunner:
    """Owns the observer + report dir for a whole suite of scenarios."""

    def __init__(self, suite_name: str, report_root: Path):
        self.suite_name = suite_name
        self.report_dir = report_root / time.strftime(f"{suite_name}-%Y%m%d-%H%M%S")
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.obs = for_current_device()
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
        ctx = RunContext(obs=self.obs, report_dir=self.report_dir)
        t0 = time.monotonic()

        # Setup + steps run on a worker thread so `Scenario.timeout_s` is a
        # hard wall — a wedged adb broadcast / debug-server GET inside pump()
        # would otherwise hang the whole suite. On expiry the drive abort flag
        # unblocks an in-flight pump(); a step stuck inside a blocking
        # subprocess call can outlive the grace join (Python threads aren't
        # killable), in which case we record the timeout and move on — the
        # per-call subprocess timeouts in qa.adb / qa.devices bound how long
        # the orphan can linger.
        outcome: dict[str, Any] = {"step": -1, "failure": "", "errored": False}

        def _work() -> None:
            try:
                if scenario.setup:
                    scenario.setup(ctx)
                for i, step in enumerate(scenario.steps):
                    outcome["step"] = i
                    step(ctx)
            except AssertionFailure as af:
                outcome["failure"] = str(af)
            except DriveAborted:
                pass  # runner-initiated; the timeout message is recorded below
            except Exception as e:
                outcome["failure"] = f"unexpected {type(e).__name__}: {e}\n{traceback.format_exc()}"
                outcome["errored"] = True

        drive_mod.clear_abort()
        worker = threading.Thread(target=_work, daemon=True,
                                  name=f"scenario:{scenario.name}")
        worker.start()
        worker.join(scenario.timeout_s)
        timed_out = worker.is_alive()
        if timed_out:
            drive_mod.request_abort()
            # Short grace join: an aborted pump() unblocks within one fix
            # interval; anything still alive after this is stuck in a blocking
            # call we can't interrupt, and waiting longer wouldn't change that.
            worker.join(2.0)

        failure_msg = str(outcome["failure"])
        if timed_out:
            step_idx = outcome["step"]
            step_name = ""
            if 0 <= step_idx < len(scenario.steps):
                step_name = f" ({getattr(scenario.steps[step_idx], '__name__', '?')})"
            stuck = " — step is still blocked, likely a wedged adb/simctl call" \
                if worker.is_alive() else ""
            failure_msg = (f"scenario timed out after {scenario.timeout_s:.0f}s "
                           f"at step {step_idx}{step_name}{stuck}")

        try:
            if scenario.teardown:
                scenario.teardown(ctx)
        except Exception as e:
            if not failure_msg:
                failure_msg = f"teardown failed: {e}"

        passed = not failure_msg
        # A timeout is reported as a failure, not an error; only an unexpected
        # exception from the worker counts as an error.
        errored = bool(outcome["errored"]) and not timed_out
        result = ScenarioResult(
            name=scenario.name,
            passed=passed,
            duration_s=time.monotonic() - t0,
            failure_message=failure_msg,
            failure_step=int(outcome["step"]) if failure_msg else -1,
            recent_logs=self.obs.snapshot_recent(200),
            errored=errored,
        )
        self.results.append(result)
        return result


# ─────────────────────────── reusable step factories ───────────────────────────


def step_drive(plan: DrivePlan, *, compression: float = 1.0) -> Step:
    """Pump a DrivePlan via the app's debug feed (`Device.feed_point`).
    Blocks until the plan ends."""
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
