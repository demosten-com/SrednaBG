# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Retention 'none' records nothing.

With history retention set to `none`, a full zone traversal must leave the
history DB empty — the recorder is gated off and existing history is purged.

Asserts:
  1. After driving a full traversal, `DUMP_HISTORY` reports count == 0.
"""

from __future__ import annotations

from ...assertions import expect, expect_crash_free
from ...events import HistoryDump
from ...runner import RunContext, Scenario, step_drive, step_lambda
from ...settings import set_setting, stop_tracking
from . import _helpers


def build() -> Scenario:
    plan = _helpers.zone_plan()

    def setup(ctx: RunContext) -> None:
        # 'none' both purges existing history and gates the recorder off.
        _helpers.begin_tracking(ctx, retention="none")
        ctx.obs.clear()

    def dump(ctx: RunContext) -> None:
        _helpers.dump_after_settle(ctx)

    def asserts(ctx: RunContext) -> None:
        expect(
            ctx.obs,
            HistoryDump,
            where=lambda e: e.count == 0,
            within_s=10,
            description="retention=none records nothing (count == 0)",
        )

    def teardown(ctx: RunContext) -> None:
        stop_tracking()
        # Restore the default so the next scenario in the suite records again.
        try:
            set_setting("history_retention", "3months", obs=ctx.obs)
        except Exception:
            pass
        expect_crash_free(ctx.obs)

    return Scenario(
        name="history.retention_none",
        steps=[
            step_lambda("setup", setup),
            step_drive(plan, compression=1.0),
            step_lambda("dump", dump),
            step_lambda("asserts", asserts),
        ],
        teardown=teardown,
        timeout_s=plan.duration_ms / 1000 + 90,
    )
