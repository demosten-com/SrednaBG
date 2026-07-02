# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""History records a completed zone traversal.

Drives one within-limit traversal of `trakiya-01-east`, then dumps the
history DB and asserts a record exists for that zone with a "within limit"
verdict and an average close to the driven speed.

Asserts:
  1. `DUMP_HISTORY` reports count >= 1.
  2. The latest record is the driven zone, verdict `over=false`.
  3. Its stored average is within tolerance of the driven speed.
"""

from __future__ import annotations

from ...assertions import expect, expect_crash_free
from ...events import HistoryDump
from ...runner import RunContext, Scenario, step_drive, step_lambda
from ...settings import stop_tracking, set_setting
from . import _helpers

AVG_TOLERANCE_KMH = 20.0


def build() -> Scenario:
    plan = _helpers.zone_plan()

    def setup(ctx: RunContext) -> None:
        _helpers.begin_tracking(ctx, retention="3months")
        # Start from an empty store so the count assertion is unambiguous.
        _helpers.reset_history(ctx)
        set_setting("history_retention", "3months", obs=ctx.obs)
        ctx.obs.clear()

    def dump(ctx: RunContext) -> None:
        _helpers.dump_after_settle(ctx)

    def asserts(ctx: RunContext) -> None:
        expect(
            ctx.obs,
            HistoryDump,
            where=lambda e: (
                e.count >= 1
                and e.zone == _helpers.ZONE_ID
                and e.over_limit is False
                and e.avg_kmh is not None
                and abs(e.avg_kmh - _helpers.WITHIN_LIMIT_KMH) <= AVG_TOLERANCE_KMH
            ),
            within_s=10,
            description=(
                f"history records {_helpers.ZONE_ID} within-limit, "
                f"avg ~{_helpers.WITHIN_LIMIT_KMH:.0f} km/h"
            ),
        )

    def teardown(ctx: RunContext) -> None:
        stop_tracking()
        expect_crash_free(ctx.obs)

    return Scenario(
        name="history.records_traversal",
        steps=[
            step_lambda("setup", setup),
            step_drive(plan, compression=1.0),
            step_lambda("dump", dump),
            step_lambda("asserts", asserts),
        ],
        teardown=teardown,
        timeout_s=plan.duration_ms / 1000 + 90,
    )
