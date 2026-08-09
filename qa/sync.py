# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Sync test helpers — wraps the platform's debug sync surface + map integrity.

The harness uses three sync flows:

1. Happy path: trigger SYNC_X, wait for `DebugSync` event, assert
   outcome was Updated/UpToDate.
2. Failure path: kill connectivity, trigger SYNC_X, assert Failed.
3. Map integrity: after a successful SYNC_MAP, verify the on-disk styles
   (style-light.json + style-dark.json) and bulgaria.mbtiles are present +
   non-empty. On Android the styles must also be placeholder-rewritten on
   disk; iOS rewrites them in memory at load time, so leftover `{…_URI}`
   placeholders there are expected (see `MapIntegrityResult`).

All operations route through the active Device so the Android + iOS
backends share the same call sites.
"""

from __future__ import annotations

import queue
import time
from typing import Optional

from . import device as device_mod
from .device import MapIntegrityResult
from .events import SyncResult
from .log_observer import LogObserver


# A sync that ends in `UpToDate` is one `/api/version` round trip and lands in
# a second or two; a *full re-fetch* pulls the whole catalog and persists every
# zone, and neither platform's debug surface blocks the trigger call until it's
# done (Android `goAsync`, iOS fire-and-forget) — the wait below is the only
# deadline it has to beat. On a nightly box running both platforms at once that
# has been measured well past 20 s, so re-fetch waits get their own budget.
REFETCH_TIMEOUT_S = 45.0


def force_sync_zones() -> None:
    device_mod.current().force_sync_zones()


def force_sync_map() -> None:
    device_mod.current().force_sync_map()


def wait_for_sync(
    obs: LogObserver,
    action_suffix: str,
    *,
    timeout_s: float = 30.0,
    collect: Optional[list] = None,
) -> SyncResult:
    """Block until a `DebugSync` event shows the action completed.

    `action_suffix` is the short tail (`SYNC_ZONES`, `SYNC_MAP`).

    Pass `collect` to keep the events consumed along the way. Everything the
    app logs *during* a sync — the zones-loaded count, an unusable-zone drop —
    arrives on the queue **before** the `DebugSync` line that closes it, so a
    caller that drains afterwards sees an empty queue and asserts vacuously
    (this is exactly how `sync.zones_all_usable` first passed against data it
    was written to reject).
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            ev = obs.queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if isinstance(ev, SyncResult) and ev.action == action_suffix:
            return ev
        if collect is not None:
            collect.append(ev)
    raise TimeoutError(f"no DebugSync result for {action_suffix} within {timeout_s}s")


def wait_for_sync_outcome(
    obs: LogObserver, action_suffix: str, outcome: str, *, timeout_s: float = 30.0
) -> SyncResult:
    """Block until a `DebugSync` event for the action reports `outcome`.

    Unlike `wait_for_sync`, a result with a *different* outcome is skipped
    (and remembered), not returned: a prior scenario's in-flight sync can
    complete after this scenario cleared the buffer — app-side async plus
    log-stream latency — so the first event seen may be stale. A genuinely
    wrong outcome still fails loudly: the TimeoutError names every outcome
    that was observed instead.
    """
    seen: list[str] = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            ev = obs.queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if isinstance(ev, SyncResult) and ev.action == action_suffix:
            if ev.outcome == outcome:
                return ev
            seen.append(f"{ev.outcome}({ev.detail})" if ev.detail else ev.outcome)
    raise TimeoutError(
        f"no DebugSync {action_suffix} with outcome {outcome} within {timeout_s:g}s "
        f"(saw: {', '.join(seen) if seen else 'nothing'})"
    )


# ──────────────────────────── network toggles ────────────────────────────


def go_offline() -> None:
    device_mod.current().go_offline()


def go_online(*, settle_timeout_s: float = 15.0) -> None:
    device_mod.current().go_online()


# ──────────────────────────── map integrity ────────────────────────────


def check_map_integrity() -> MapIntegrityResult:
    return device_mod.current().check_map_integrity()


def assert_map_integrity_ok(result: MapIntegrityResult) -> None:
    from .assertions import AssertionFailure
    problems: list[str] = []
    if not result.style_present:
        problems.append("map style file missing (need style-light.json + style-dark.json)")
    if not result.mbtiles_present:
        problems.append("bulgaria.mbtiles missing")
    if result.placeholders_remaining and not result.placeholders_expected:
        problems.append(f"unrewritten placeholders in map styles: {result.placeholders_remaining}")
    if result.mbtiles_present and result.mbtiles_size_bytes < 1_000_000:
        problems.append(f"bulgaria.mbtiles suspiciously small: {result.mbtiles_size_bytes} bytes")
    if problems:
        raise AssertionFailure(f"map integrity check failed: {'; '.join(problems)}")
