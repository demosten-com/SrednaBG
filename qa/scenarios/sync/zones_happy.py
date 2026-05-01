# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Sync zones happy path: server reachable, force a sync, expect Updated or UpToDate."""

from __future__ import annotations

import time

from ... import sync
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        ctx.obs.clear()
        sync.force_sync_zones()
        result = sync.wait_for_sync(ctx.obs, "SYNC_ZONES", timeout_s=20)
        if result.outcome not in ("Updated", "UpToDate"):
            raise AssertionFailure(
                f"expected Updated/UpToDate, got {result.outcome} (detail={result.detail})"
            )

    def teardown(ctx: RunContext) -> None:
        expect_crash_free(ctx.obs)

    return Scenario(
        name="sync.zones_happy",
        steps=[step_lambda("force_zones_sync", go)],
        teardown=teardown,
        timeout_s=60,
    )
