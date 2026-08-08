# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Sync zones offline path: kill connectivity, force sync, expect Failed.

Restores network on teardown so subsequent scenarios aren't broken.
"""

from __future__ import annotations


from ... import sync
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        ctx.obs.clear()
        sync.go_offline()
        try:
            sync.force_sync_zones()
            # A previous scenario's restore-sync can land its UpToDate after
            # the clear() above, so the first SYNC_ZONES event may be stale —
            # accept only Failed and let the timeout name anything else seen.
            try:
                sync.wait_for_sync_outcome(ctx.obs, "SYNC_ZONES", "Failed", timeout_s=30)
            except TimeoutError as exc:
                raise AssertionFailure(f"expected Failed while offline: {exc}") from exc
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
