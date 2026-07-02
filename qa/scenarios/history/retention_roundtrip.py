# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""The `settings-history-retention` key round-trips.

Sets each of the four retention values and confirms the app applied it (the
`DebugSettings` `set history_retention=<value>` line). Fast, no driving —
guards the setting plumbing (repository key + debug setter).

Asserts:
  1. Each of none / 1month / 3months / 6months round-trips through
     `set_setting` and is confirmed via a `SettingChanged` event.
"""

from __future__ import annotations

import time

from ...assertions import expect, expect_crash_free
from ...events import SettingChanged
from ...runner import RunContext, Scenario, step_lambda
from ... import device as device_mod
from ...settings import set_setting

VALUES = ["1month", "6months", "none", "3months"]


def build() -> Scenario:
    def setup(ctx: RunContext) -> None:
        device_mod.current().start_main()
        time.sleep(1.5)
        ctx.obs.clear()

    def roundtrip(ctx: RunContext) -> None:
        for value in VALUES:
            # Fire without `obs=` so `set_setting` doesn't consume the
            # SettingChanged from the queue — `expect` below is the sole
            # consumer that confirms it. (Passing `obs=` here double-waits:
            # on the fast iOS debug path set_setting drains the only event and
            # the following expect then times out.)
            set_setting("history_retention", value)
            expect(
                ctx.obs,
                SettingChanged,
                where=lambda e, v=value: e.key == "history_retention" and e.value == v,
                within_s=5,
                description=f"history_retention set to {value}",
            )

    def teardown(ctx: RunContext) -> None:
        expect_crash_free(ctx.obs)

    return Scenario(
        name="history.retention_roundtrip",
        steps=[
            step_lambda("setup", setup),
            step_lambda("roundtrip", roundtrip),
        ],
        teardown=teardown,
        timeout_s=60,
    )
