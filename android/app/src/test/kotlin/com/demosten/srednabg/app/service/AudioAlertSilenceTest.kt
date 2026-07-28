// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.SpeedStatus
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import com.demosten.srednabg.core.ZoneState
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.TestFactory

/**
 * Every transition into or out of [ZoneState.Unmeasured] is announced as
 * nothing. That silence is a **decision** — see [isUnmeasuredTransition] — and
 * this pins it so the intent lives in a test rather than only in a comment.
 *
 * No such pair matches a later branch of `AudioAlertManager.onZoneStateChanged`'s
 * `when` today, so deleting the guard would still fall off the end silently.
 * That is exactly what this locks: the day someone adds a branch broad enough to
 * claim one of these pairs (an `Exiting → *` catch-all, a `* → Outside` recap),
 * it fails here rather than in a drive.
 *
 * iOS peer: `AnnouncementPolicyTests.everyUnmeasuredTransitionIsSilent`, which
 * asserts the same matrix against the whole pure `AnnouncementPolicy.decide`.
 *
 * The split is deliberate, not an oversight: the two platforms put the gate at
 * different layers, so each test has to sit where its platform's decision is
 * actually made. Android's lives in the `AudioAlertManager` `when` (there is no
 * pure policy object to hand it to), so this asserts the boolean gate —
 * *"is this pair silent?"*. iOS's lives in the pure `AnnouncementPolicy`, so
 * that one asserts the whole decision is empty — *"is nothing announced, and no
 * clock updated?"*. Hoisting either into the shared core would mean moving one
 * platform's announcement layer, which buys nothing the pair already gives.
 * Change both together.
 */
class AudioAlertSilenceTest {

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
    private val zoneB = zoneA.copy(id = "trakiya-02-east", road = "АМ Тракия (Б)")

    private fun unmeasured(zone: Zone = zoneA) =
        ZoneState.Unmeasured(zone = zone, distanceRemaining = 5000.0)

    private fun inZone(zone: Zone = zoneA) = ZoneState.InZone(
        zone = zone,
        entryTime = 0L,
        distanceTraveled = 1000.0,
        speedStatus = SpeedStatus(
            avgSpeed = 152.0,
            maxSpeedForRemainder = 140.0,
            distanceRemaining = 7000.0,
            timeRemaining = 0.0,
            isOverLimit = true,
        ),
        distanceRemaining = 7000.0,
    )

    private fun exiting(zone: Zone = zoneA) = ZoneState.Exiting(zone, 132.0)

    @TestFactory
    fun `transitions in or out of Unmeasured are always silent`(): List<DynamicTest> = listOf(
        "Outside -> Unmeasured" to (ZoneState.Outside to unmeasured()),
        "Unmeasured -> Unmeasured" to (unmeasured() to unmeasured()),
        "Unmeasured -> Outside" to (unmeasured() to ZoneState.Outside),
        "Unmeasured -> InZone" to (unmeasured() to inZone()),
        "InZone -> Unmeasured" to (inZone() to unmeasured()),
        "Exiting -> Unmeasured" to (exiting() to unmeasured()),
        "Unmeasured -> Exiting" to (unmeasured() to exiting()),
        "Unmeasured(A) -> Unmeasured(B)" to (unmeasured() to unmeasured(zoneB)),
    ).map { (label, pair) ->
        DynamicTest.dynamicTest(label) {
            assertTrue(
                isUnmeasuredTransition(pair.first, pair.second),
                "$label must be recognised as silent",
            )
        }
    }

    @TestFactory
    fun `measured transitions are not claimed by the silence branch`(): List<DynamicTest> = listOf(
        "Outside -> InZone" to (ZoneState.Outside to inZone()),
        "InZone -> InZone" to (inZone() to inZone()),
        "InZone -> Exiting" to (inZone() to exiting()),
        "Exiting -> InZone" to (exiting() to inZone(zoneB)),
        "Exiting -> Outside" to (exiting() to ZoneState.Outside),
        "Outside -> Outside" to (ZoneState.Outside to ZoneState.Outside),
    ).map { (label, pair) ->
        DynamicTest.dynamicTest(label) {
            // Anti-vacuous half: a guard that swallowed everything would satisfy
            // the matrix above while silencing the whole announcement pipeline.
            assertFalse(
                isUnmeasuredTransition(pair.first, pair.second),
                "$label must reach the announcement branches",
            )
        }
    }
}
