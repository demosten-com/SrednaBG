// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class ZoneDataRecencyTest {

    private val older = "2026-07-13T06:10:40Z"
    private val newer = "2026-07-17T11:51:47Z"

    // isStrictlyNewer

    @Test
    fun `isStrictlyNewer true when candidate is later`() {
        assertEquals(true, ZoneDataRecency.isStrictlyNewer(newer, older))
    }

    @Test
    fun `isStrictlyNewer false when candidate is earlier`() {
        assertEquals(false, ZoneDataRecency.isStrictlyNewer(older, newer))
    }

    @Test
    fun `isStrictlyNewer false when equal`() {
        assertEquals(false, ZoneDataRecency.isStrictlyNewer(newer, newer))
    }

    @Test
    fun `isStrictlyNewer null on legacy or malformed versions`() {
        assertNull(ZoneDataRecency.isStrictlyNewer("", newer))
        assertNull(ZoneDataRecency.isStrictlyNewer(newer, ""))
        assertNull(ZoneDataRecency.isStrictlyNewer("v1", newer))
        // Non-zero-padded / missing Z would break lexicographic ordering, so
        // they must be rejected, not compared.
        assertNull(ZoneDataRecency.isStrictlyNewer("2026-7-17T11:51:47Z", older))
        assertNull(ZoneDataRecency.isStrictlyNewer("2026-07-17T11:51:47", older))
    }

    // decide

    @Test
    fun `decide up to date when hashes match`() {
        assertEquals(
            ZoneSyncDecision.UP_TO_DATE,
            ZoneDataRecency.decide("h1", older, "h1", newer),
        )
    }

    @Test
    fun `decide hash match wins even when remote version is newer`() {
        assertEquals(
            ZoneSyncDecision.UP_TO_DATE,
            ZoneDataRecency.decide("h1", newer, "h1", older),
        )
    }

    @Test
    fun `decide applies remote when hash differs and remote is newer`() {
        assertEquals(
            ZoneSyncDecision.APPLY_REMOTE,
            ZoneDataRecency.decide("h2", newer, "h1", older),
        )
    }

    @Test
    fun `decide skips remote when hash differs and remote is older`() {
        assertEquals(
            ZoneSyncDecision.SKIP_REMOTE_STALE,
            ZoneDataRecency.decide("h2", older, "h1", newer),
        )
    }

    @Test
    fun `decide applies remote when hash differs and versions are equal`() {
        // Equal version + different hash can only mean corrupted local state
        // (a fresh scrape always carries a new timestamp) — the server repairs.
        assertEquals(
            ZoneSyncDecision.APPLY_REMOTE,
            ZoneDataRecency.decide("h2", newer, "h1", newer),
        )
    }

    @Test
    fun `decide applies remote when either version is not comparable`() {
        assertEquals(
            ZoneSyncDecision.APPLY_REMOTE,
            ZoneDataRecency.decide("h2", older, "h1", "v1"),
        )
        assertEquals(
            ZoneSyncDecision.APPLY_REMOTE,
            ZoneDataRecency.decide("h2", "", "h1", newer),
        )
    }

    @Test
    fun `decide applies remote when cached hash is empty`() {
        assertEquals(
            ZoneSyncDecision.APPLY_REMOTE,
            ZoneDataRecency.decide("h1", newer, "", ""),
        )
        // Even an equal empty hash means "nothing cached" — fetch.
        assertEquals(
            ZoneSyncDecision.APPLY_REMOTE,
            ZoneDataRecency.decide("", newer, "", ""),
        )
    }

    // shouldReseedFromBundle

    @Test
    fun `reseed when bundle is strictly newer with different hash`() {
        assertTrue(ZoneDataRecency.shouldReseedFromBundle("h2", newer, "h1", older))
    }

    @Test
    fun `no reseed when bundle hash matches cached`() {
        assertFalse(ZoneDataRecency.shouldReseedFromBundle("h1", newer, "h1", older))
    }

    @Test
    fun `no reseed when bundle is older or equal`() {
        assertFalse(ZoneDataRecency.shouldReseedFromBundle("h2", older, "h1", newer))
        assertFalse(ZoneDataRecency.shouldReseedFromBundle("h2", newer, "h1", newer))
    }

    @Test
    fun `no reseed when versions are not comparable`() {
        assertFalse(ZoneDataRecency.shouldReseedFromBundle("h2", newer, "h1", "v1"))
        assertFalse(ZoneDataRecency.shouldReseedFromBundle("h2", "", "h1", older))
    }
}
