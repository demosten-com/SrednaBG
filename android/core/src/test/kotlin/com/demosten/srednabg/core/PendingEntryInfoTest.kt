// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * The entry-candidate side channel ([ZoneDetector.pendingEntryInfo]) that the
 * announcement layer speaks from, so the driver hears the entry where they cross
 * the camera rather than [ZoneDetector.ENTRY_CONFIRM_DISTANCE_M] later.
 *
 * These tests pin the two properties the announcement depends on:
 *
 * - it appears on the **first** matching fix, while the state is still Outside;
 * - its `entryArcM` is the same value `witnessedStart` will later judge, so
 *   applying [ZoneDetector.START_WITNESS_ARC_M] to it predicts, before
 *   confirmation, whether this candidate can become a measured traversal.
 *
 * That second property is what lets the announcement stay silent for the
 * A3/Кочериново phantom while speaking early for a genuine approach.
 */
class PendingEntryInfoTest {

    @Test
    fun `no candidate exists while no zone matches`() {
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        assertNull(det.pendingEntryInfo, "A fresh detector has no candidate")

        // Far away from the zone, on no road of ours.
        det.update(GpsPoint(42.0, 23.0, 130.0, EPOCH_BASE, 90.0))
        assertNull(det.pendingEntryInfo, "An unmatched fix must not open a candidate")
    }

    @Test
    fun `a genuine approach opens a candidate at arc zero, well before confirmation`() {
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val trace = centerlineTrace(
            TRAKIYA_T10,
            fromArcM = -200.0,
            metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 2 + 200.0,
        )

        var firstCandidateIndex = -1
        var firstCandidate: PendingEntryInfo? = null
        var enteredIndex = -1
        trace.forEachIndexed { i, point ->
            val state = det.update(point)
            val candidate = det.pendingEntryInfo
            if (firstCandidate == null && candidate != null) {
                firstCandidateIndex = i
                firstCandidate = candidate
                assertTrue(
                    state is ZoneState.Outside,
                    "The candidate must appear while still Outside — the whole point is to " +
                        "announce before the traversal opens, got $state",
                )
            }
            if (enteredIndex < 0 && state is ZoneState.InZone) enteredIndex = i
        }

        assertNotNull(firstCandidate, "A car driving the road must open a candidate")
        val candidate = firstCandidate!!
        assertEquals(TRAKIYA_T10.id, candidate.zone.id)
        assertTrue(
            candidate.entryArcM <= ZoneDetector.START_WITNESS_ARC_M,
            "A genuine approach projects to arc ~0, so the announcement guard must pass it — " +
                "got ${candidate.entryArcM}m against ${ZoneDetector.START_WITNESS_ARC_M}m",
        )

        // The announcement moves earlier by the whole confirmation window: the
        // candidate opens several fixes before the traversal does. Without this
        // the side channel would be pointless.
        assertTrue(enteredIndex > firstCandidateIndex, "The traversal must open after the candidate")
        val stepM = 36.0
        val gainedM = (enteredIndex - firstCandidateIndex) * stepM
        assertTrue(
            gainedM >= ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 0.8,
            "Announcing on the candidate must save roughly the confirmation window — " +
                "expected at least ${ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 0.8}m, got ${gainedM}m",
        )
    }

    @Test
    fun `the candidate is cleared once the traversal opens`() {
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val state = driveAlongCenterline(
            det, TRAKIYA_T10,
            fromArcM = -200.0,
            metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 2 + 200.0,
        )
        assertTrue(state is ZoneState.InZone, "Expected a measured traversal, got $state")
        assertNull(
            det.pendingEntryInfo,
            "A graduated candidate must not linger — otherwise the announcement layer would " +
                "see it as still pending and could re-announce",
        )
    }

    @Test
    fun `a road clipping the band mid-zone exposes a candidate the arc guard rejects`() {
        // The A3 Струма / i1-02-north phantom (real drive, 2026-07-26). It is
        // ENTRY_CONFIRM_DISTANCE_M that stops it opening a traversal — but the
        // announcement no longer waits for confirmation, so the *announcement*
        // needs its own reason to stay quiet. That reason is entryArcM: the
        // clipping road first matches deep inside the zone, far past
        // START_WITNESS_ARC_M, whereas a genuine approach matches at arc ~0.
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val trace = centerlineTrace(
            TRAKIYA_T10,
            fromArcM = 2_000.0,
            metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 0.6,
            lateralOffsetM = 60.0,
        )

        var candidate: PendingEntryInfo? = null
        trace.forEach { point ->
            val state = det.update(point)
            assertTrue(state is ZoneState.Outside, "The clipping road must never open a traversal, got $state")
            if (candidate == null) candidate = det.pendingEntryInfo
        }

        assertNotNull(candidate, "The clipping road does match, so a candidate does open")
        val seen = candidate!!
        assertTrue(
            seen.entryArcM > ZoneDetector.START_WITNESS_ARC_M,
            "The phantom's first match sits deep in the zone, so the announcement guard must " +
                "reject it — got ${seen.entryArcM}m against ${ZoneDetector.START_WITNESS_ARC_M}m",
        )
    }
}
