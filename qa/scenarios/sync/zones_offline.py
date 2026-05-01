# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Sync zones offline path: kill connectivity, force sync, expect Failed.

Restores network on teardown so subsequent scenarios aren't broken.
"""

from __future__ import annotations

import time

from ... import sync
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        ctx.obs.clear()
        sync.go_offline()
        try:
            sync.force_sync_zones()
            result = sync.wait_for_sync(ctx.obs, "SYNC_ZONES", timeout_s=30)
            if result.outcome != "Failed":
                raise AssertionFailure(
                    f"expected Failed while offline, got {result.outcome} (detail={result.detail})"
                )
        finally:
            sync.go_online()

    def teardown(ctx: RunContext) -> None:
        sync.go_online()  # belt + suspenders
        expect_crash_free(ctx.obs)

    return Scenario(
        name="sync.zones_offline",
        steps=[step_lambda("force_offline_sync", go)],
        teardown=teardown,
        timeout_s=120,
    )
