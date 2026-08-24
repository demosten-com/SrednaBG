// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import com.demosten.srednabg.core.PendingEntryInfo
import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.SpeedStatus
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import com.demosten.srednabg.core.ZoneState
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * The two stateful rules behind announcing an entry on the detector's *candidate*
 * rather than on the confirmed traversal — see
 * `LocationTrackingService.announceProvisionalEntry` and
 * `AudioAlertManager.onProvisionalEntry`.
 *
 * Both are pure functions precisely so they can be pinned here: getting either
 * wrong is silent in a way no crash or lint would catch — a duplicated entry
 * announcement, or worse, a real zone driven with no announcement at all.
 */
class ProvisionalEntryGateTest {

    private val zoneA = Zone(
        id = "trakiya-01-east",
        road = "АМ Тракия",
        roadLatin = "Trakiya",
        direction = "east",
        description = "test",
        start = ZoneEndpoint(lat = 42.0, lng = 25.0),
        end = ZoneEndpoint(lat = 42.0, lng = 25.1),
        distanceM = 8000,
        speedLimits = SpeedLimits(car = 140, truck = 90, bus = 100, motorcycle = 140),
        centerline = listOf(listOf(42.0, 25.0), listOf(42.0, 25.1)),
        source = "test",
        lastVerified = "2026-06-10",
    )
    private val zoneB = zoneA.copy(id = "trakiya-02-east")

    private fun candidate(zone: Zone = zoneA, arcM: Double = 0.0) = PendingEntryInfo(zone, arcM)

    private fun inZone(zone: Zone = zoneA) = ZoneState.InZone(
        zone = zone,
        entryTime = 0L,
        distanceTraveled = 1000.0,
        speedStatus = SpeedStatus(
            avgSpeed = 120.0,
            maxSpeedForRemainder = 140.0,
            distanceRemaining = 7000.0,
            timeRemaining = 0.0,
            isOverLimit = false,
        ),
        distanceRemaining = 7000.0,
    )

    @Test
    fun `a freshly opened candidate announces`() {
        assertTrue(isNewProvisionalCandidate(null, candidate(), ZoneState.Outside))
    }

    @Test
    fun `extending the same candidate stays silent`() {
        // Every subsequent fix of the ~300 m confirmation window re-reports the
        // same candidate. Announcing on each would repeat the entry line at 1-2 Hz.
        assertFalse(isNewProvisionalCandidate(zoneA.id, candidate(), ZoneState.Outside))
    }

    @Test
    fun `switching to a different zone's candidate announces again`() {
        assertTrue(isNewProvisionalCandidate(zoneA.id, candidate(zoneB), ZoneState.Outside))
    }

    @Test
    fun `a fix that itself opened the traversal stays silent`() {
        // The co-located handover bypasses entry confirmation, so the candidate
        // opens and confirms on the same fix. The Exiting -> InZone branch already
        // announces that entry with QUEUE_ADD, after the previous zone's
        // exit-with-average; announcing here too would duplicate it and, being
        // QUEUE_FLUSH, would cut the exit line off mid-sentence.
        assertFalse(isNewProvisionalCandidate(null, candidate(zoneB), inZone(zoneB)))
    }

    @Test
    fun `a confirmed entry is skipped only while the provisional is fresh`() {
        val spokenAt = 1_000_000L
        assertTrue(
            isProvisionalStillFresh(zoneA.id, zoneA.id, spokenAt, spokenAt + 9_000L),
            "Confirmation arrives seconds after the candidate — the entry must not be spoken twice",
        )
    }

    @Test
    fun `a stale provisional never swallows a genuine later entry`() {
        // The failure this guards: an abandoned candidate leaves the id set with
        // nothing to clear it. Without the window, driving that same zone for real
        // an hour later would be completely silent.
        val spokenAt = 1_000_000L
        assertFalse(
            isProvisionalStillFresh(
                zoneA.id, zoneA.id, spokenAt, spokenAt + PROVISIONAL_REPEAT_WINDOW_MS + 1,
            ),
        )
    }

    @Test
    fun `a different zone is never considered already announced`() {
        val spokenAt = 1_000_000L
        assertFalse(isProvisionalStillFresh(zoneB.id, zoneA.id, spokenAt, spokenAt + 1_000L))
        assertFalse(isProvisionalStillFresh(zoneA.id, null, 0L, spokenAt))
    }
}
