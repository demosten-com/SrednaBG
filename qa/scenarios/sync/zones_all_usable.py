# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Every zone the server serves must be one the app can actually use.

The 2026-08 outage this guards: a section on Път I-8 failed to merge upstream
(the road was missing from `roads.ROAD_AXIS` / `ROAD_DIRECTIONS`, so the
coordinate-bearing sources and BG TOLL inferred *different* direction labels
and landed in different match groups). It published twice — once with
placeholder `(0, 0)` endpoints and an **empty centerline**, once with only a
`car` speed limit. Consequences, neither of which any existing scenario saw:

* Android: two zero-point LineStrings made MapLibre reject the **entire** zone
  FeatureCollection ("A line string must have two or more coordinate points"),
  so all 76 zones vanished from the map while sync happily reported success.
* iOS: the missing `truck` / `bus` keys threw `keyNotFound` out of the
  `ZonesResponse` decode, failing every sync from that day onward.

Current builds defend against both — `ZoneSanitizer` drops the unusable zones
per-zone, `SpeedLimits`' decoder falls back to the car limit — but that is a
*tourniquet*, not a fix, and it protects only builds that carry it. **1.x is
what the stores serve**, and 1.x has neither defence, so bad data is a fleet
outage that no app update can reach: the wire format is the only thing between
the cron and every published install. Which makes this scenario's real job
adversarial — it must fail on data *this* build is perfectly happy with.

1. Force a real zone sync against the production backend → require `Updated`.
   `Failed` is a payload we can't decode; `UpToDate` means nothing was fetched
   and the checks below would inspect nothing.
2. Assert no `zones repaired` line. Ordered first because it is the one QA
   would otherwise miss: the zone looks healthy here and kills 1.x.
3. Assert no `zones dropped` line — geometry the app can't use at all.

Both lines are silent against healthy data, so any occurrence is a finding, and
each names the ids so the fix (normally one entry in `roads.ROAD_AXIS` /
`ROAD_DIRECTIONS`, then a cron re-run) is immediate. The scraper's
`publish_guard_errors` is meant to stop such data ever reaching the wire; this
is the on-device check that it did.

Cross-platform: both clients emit identical `zones {dropped,repaired} (n=…)
ids=[…] origin=…` bodies on the `SrednaBG.Loc` channel.
"""

from __future__ import annotations

from ... import settings, sync
from ...assertions import AssertionFailure, expect_crash_free
from ...events import ZonesDropped, ZonesRepaired
from ...runner import RunContext, Scenario, step_lambda

# Non-empty and structurally hash-shaped, but can never equal a real server
# digest — guarantees the gate falls through to a full fetch, so the zones are
# genuinely re-parsed rather than short-circuited as up-to-date.
_SENTINEL_HASH = "sha256:qa-all-usable-00000000000000000000000000000000000000"

# Older than any real scrape, so `ZoneDataRecency` can't classify the server as
# stale. Without this the scenario is **vacuous** whenever the app bundles a
# fresher scrape than the weekly cron has published (the normal state right
# after a `refresh-zones.sh`): the recency gate returns UpToDate, nothing is
# fetched, no zone is sanitized, and the tripwire "passes" having inspected
# nothing. Requiring `Updated` below turns that into a failure instead.
_ANCIENT_VERSION = "2020-01-01T00:00:00Z"


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        # Poison the cached hash *and* backdate the cached version so both
        # gates fall through and the full catalog is really fetched, decoded
        # and sanitized — the only state in which this scenario can see
        # anything.
        settings.set_setting("cached_zone_hash", _SENTINEL_HASH)
        settings.set_setting("cached_zone_version", _ANCIENT_VERSION)
        ctx.obs.clear()
        sync.force_sync_zones()
        # `collect` matters: the drop line is logged *during* the sync, so it
        # reaches the queue before the closing DebugSync event and would be
        # consumed (and discarded) by the wait itself.
        during: list = []
        result = sync.wait_for_sync(
            ctx.obs, "SYNC_ZONES", timeout_s=sync.REFETCH_TIMEOUT_S, collect=during
        )
        if result.outcome != "Updated":
            raise AssertionFailure(
                "the served catalog must be fetched and decoded here — a "
                "payload the client can't decode reports Failed, and UpToDate "
                "means nothing was inspected so the check below would be "
                f"vacuous: got {result.outcome} (detail={result.detail})"
            )

        during.extend(ctx.obs.drain())

        # Repairs first: this is the class that looks *healthy* on a current
        # build and is fatal on the 1.x installs the stores actually serve, so
        # it is the one QA is most likely to miss. On iOS 1.x a single zone
        # missing `truck`/`bus` throws `keyNotFound` and fails the decode of
        # the entire catalog — sync dies for every published user, permanently,
        # with no client-side recovery. Our own build sails through it.
        repaired = [ev for ev in during if isinstance(ev, ZonesRepaired)]
        if repaired:
            named = ", ".join(i for ev in repaired for i in ev.ids)
            total = sum(ev.count for ev in repaired)
            raise AssertionFailure(
                f"the backend is serving {total} zone(s) with a missing "
                f"truck/bus speed limit ({named}). This build repairs them "
                f"from the car limit, but the shipped 1.x clients do not: iOS "
                f"1.x fails the whole /api/zones decode, and Android 1.x reads "
                f"the gap as a 0 km/h limit. Fix the merge and re-publish — "
                f"the scraper's publish guard should have refused this."
            )

        dropped = [ev for ev in during if isinstance(ev, ZonesDropped)]
        if dropped:
            named = ", ".join(i for ev in dropped for i in ev.ids)
            total = sum(ev.count for ev in dropped)
            raise AssertionFailure(
                f"the backend is serving {total} zone(s) the app cannot use "
                f"({named}) — placeholder (0, 0) endpoints, an empty "
                f"centerline, or no car limit. The client drops them so the "
                f"map still renders, but the zone is missing from the app. "
                f"Check roads.ROAD_AXIS / ROAD_DIRECTIONS covers the road, "
                f"re-run the scraper, and re-publish."
            )

    def teardown(ctx: RunContext) -> None:
        # A successful step already persisted the real server hash + version.
        # If the step failed mid-way the backdated version could still be
        # pinned, which would make every later scenario re-fetch; clear it to
        # the legacy/not-comparable value so the gate behaves normally again.
        settings.set_setting("cached_zone_version", "")
        expect_crash_free(ctx.obs)

    return Scenario(
        name="sync.zones_all_usable",
        steps=[step_lambda("served_zones_are_all_usable", go)],
        teardown=teardown,
        timeout_s=90,
    )
