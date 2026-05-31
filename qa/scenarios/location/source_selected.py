# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Flavor tripwire: assert which GPS source the installed build selects.

The app ships in two product flavors that differ only in the location
provider (see android/app/src/{aosp,gms}/.../LocationSourceFactory.kt):

  - aosp — LocationManager only ("system"). F-Droid + GitHub Releases.
  - gms  — FusedLocationProvider ("fused"), with a runtime fallback to
           "system" on AAOS or when Play Services is unavailable. Play Store.

On tracking start the flavor's `createLocationSource()` logs
`SrednaBG.LocSrc: Selecting {Fused,System}LocationSource …`, parsed into a
`LocationSourceSelected` event. This scenario starts tracking and:

  - `--flavor aosp` → asserts source == "system" (and FAILS on "fused", i.e.
    the FOSS build accidentally re-linked GMS, or the wrong APK is installed).
  - `--flavor gms`  → asserts source == "fused" (on a Google-APIs emulator;
    a plain AOSP image would legitimately fall back to "system").
  - `--flavor auto` (default) → only asserts that *a* source was selected, so
    the path is exercised and recorded without pinning the flavor.
"""

from __future__ import annotations

from typing import Optional

from ... import settings
from ...assertions import AssertionFailure, expect, expect_crash_free
from ...events import LocationSourceSelected
from ...runner import RunContext, Scenario, step_lambda


def build(expected: Optional[str] = None) -> Scenario:
    """`expected` is "system", "fused", or None (record-only / auto)."""

    def go(ctx: RunContext) -> None:
        ctx.obs.clear()
        settings.start_tracking()
        ev = expect(
            ctx.obs,
            LocationSourceSelected,
            within_s=15.0,
            description="app should log the selected GPS source on tracking start",
        )
        if expected is not None and ev.source != expected:
            raise AssertionFailure(
                f"location-source flavor mismatch: expected {expected!r} "
                f"(implied by --flavor), but the app selected {ev.source!r}. "
                "Either the wrong flavor APK is installed, or the flavor wiring "
                f"regressed (e.g. the aosp build re-linked GMS). raw={ev.raw!r}",
                ctx.obs,
            )

    def teardown(ctx: RunContext) -> None:
        settings.stop_tracking()
        expect_crash_free(ctx.obs)

    return Scenario(
        name=f"location.source_selected[{expected or 'any'}]",
        steps=[step_lambda("start_tracking_expect_location_source", go)],
        teardown=teardown,
        timeout_s=40,
    )
