# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Sync map happy path + on-disk integrity post-check.

After a successful SYNC_MAP, verifies that style.json placeholders were
rewritten and the mbtiles file is present + sane size. This guards the
"synced but app crashes on map open" failure mode.
"""

from __future__ import annotations

from ... import sync
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        ctx.obs.clear()
        sync.force_sync_map()
        result = sync.wait_for_sync(ctx.obs, "SYNC_MAP", timeout_s=120)
        if result.outcome not in ("Updated", "UpToDate"):
            raise AssertionFailure(
                f"expected Updated/UpToDate, got {result.outcome} (detail={result.detail})"
            )
        # Post-check on-disk integrity regardless of whether the sync
        # changed anything — both UpToDate and Updated should leave a
        # working bundle on disk.
        integrity = sync.check_map_integrity()
        sync.assert_map_integrity_ok(integrity)

    def teardown(ctx: RunContext) -> None:
        expect_crash_free(ctx.obs)

    return Scenario(
        name="sync.map_happy",
        steps=[step_lambda("force_map_sync", go)],
        teardown=teardown,
        timeout_s=180,
    )
