# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Wraps `qa.ui.smoke_walk` as a Scenario so it fits the suite runner."""

from __future__ import annotations

from ...assertions import expect_crash_free
from ...runner import RunContext, Scenario, step_lambda
from ...ui import UiRecorder, smoke_walk


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        recorder = UiRecorder(ctx.report_dir)
        smoke_walk(ctx.report_dir, ui=recorder)
        ctx.data["ui_screenshots"] = [c.args["path"] for c in recorder.commands
                                      if c.kind == "screenshot"]

    def teardown(ctx: RunContext) -> None:
        expect_crash_free(ctx.obs)

    return Scenario(
        name="ui.smoke_walk",
        steps=[step_lambda("walk", go)],
        teardown=teardown,
        timeout_s=60,
    )
