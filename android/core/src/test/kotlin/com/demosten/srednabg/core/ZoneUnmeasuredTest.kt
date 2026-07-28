// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * Entry provenance: a traversal is only measurable if we watched the vehicle
 * cross the start line. Everything else inside a zone is [ZoneState.Unmeasured]
 * — we say which zone it is and how much road is left, and nothing else.
 *
 * Split out of ZoneDetectorTest, which is already the largest core test file
 * (the iOS port makes the same split for SwiftLint's file-length rule).
 *
 * See ZoneDetector.START_WITNESS_ARC_M.
 */
class ZoneUnmeasuredTest {

    @Test
    fun `joining mid-zone never opens a traversal and never exits one`() {
        // The core of the change: a sustained, perfectly on-road drive that
        // simply began too far into the zone. It confirms (300 m of travel along
        // the centerline) but is not witnessed, so it graduates into Unmeasured
        // rather than InZone — and leaving it produces no Exiting, which is what
        // keeps it out of History and out of the exit announcement without any
        // suppression logic at the consumer layers.
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val states = collectAlongCenterline(
            det, TRAKIYA_T10,
            fromArcM = 5_000.0,
            metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 3,
        )

        assertTrue(states.any { it is ZoneState.Unmeasured }, "Should have become Unmeasured")
        assertTrue(states.none { it is ZoneState.InZone }, "Must never open a measured traversal")
        assertTrue(states.none { it is ZoneState.Exiting }, "Must never produce an Exiting")

        // Peel off the road: Unmeasured drops straight to Outside.
        val awayTime = EPOCH_BASE + 600_000L
        val away = det.update(GpsPoint(42.9, 24.4, 130.0, awayTime, 180.0))
        assertEquals(ZoneState.Outside, away, "Leaving an Unmeasured zone goes straight to Outside")
    }

    @Test
    fun `driving an Unmeasured zone to its end lands on Outside, not Exiting`() {
        // Exiting only ever follows InZone: there is no traversal to finalize, so
        // reaching the end camera is not an exit. Locks the invariant the
        // consumer layers rely on (no History row, no exit TTS).
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val total = polylineLengthMeters(TRAKIYA_T10.centerline)
        val startArc = 6_000.0
        val states = collectAlongCenterline(
            det, TRAKIYA_T10,
            fromArcM = startArc,
            metres = total - startArc,
        )

        assertTrue(states.any { it is ZoneState.Unmeasured }, "Should have been Unmeasured")
        assertTrue(states.none { it is ZoneState.Exiting },
            "Reaching the end of an Unmeasured zone must not fabricate an Exiting")
        assertEquals(ZoneState.Outside, states.last(), "Should have ended Outside")
    }

    @Test
    fun `a co-located successor is still measurable after an Unmeasured predecessor`() {
        // A driver who joined A mid-way still physically crosses B's entry camera,
        // so B is genuinely measurable and must open normally. What does not
        // carry over is the COLOCATED_CAMERA_M confirmation bypass — that is armed
        // in exitZone, which an Unmeasured zone never reaches — so B pays the
        // ordinary 300 m confirmation. Roughly 10 s of announcement latency in a
        // rare case; deliberately not special-cased.
        val zoneA = TRAKIYA_T10
        val zoneB = nextZoneFrom(zoneA, id = "trakiya-02-west", lengthM = 6_000.0)
        val det = ZoneDetector(listOf(zoneA, zoneB))

        val stepM = 36.0
        val speed = 130.0
        val stepMs = (stepM / (speed / 3.6) * 1000.0).toLong()
        val totalA = polylineLengthMeters(zoneA.centerline)
        val startArcA = 4_000.0

        val statesA = collectAlongCenterline(
            det, zoneA, fromArcM = startArcA, metres = totalA - startArcA,
            speedKmh = speed, stepM = stepM,
        )
        assertTrue(statesA.any { it is ZoneState.Unmeasured && it.zone.id == zoneA.id },
            "Zone A was joined mid-way, so it must be Unmeasured")
        assertTrue(statesA.none { it is ZoneState.InZone }, "Zone A must not be measured")

        val statesB = collectAlongCenterline(
            det, zoneB, fromArcM = 0.0, metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 2,
            speedKmh = speed, stepM = stepM,
            startTime = EPOCH_BASE + statesA.size * stepMs,
        )
        assertTrue(statesB.any { it is ZoneState.InZone && it.zone.id == zoneB.id },
            "Zone B's entry camera *was* crossed, so B must be measured, got $statesB")
        assertTrue(statesB.none { it is ZoneState.Unmeasured },
            "Zone B starts at arc 0 — it must never read as a mid-zone join")
    }

    @Test
    fun `a co-located handover counts as witnessed even when the first fix lands late`() {
        // Driving A to its end IS crossing B's start camera, so a handover is
        // witnessed by construction — whatever arc B's first fix happens to land
        // at. Without the `|| handedOver` clause a coarse fix right after the
        // shared camera could downgrade a genuinely measurable zone to Unmeasured
        // and silently swallow its entry announcement.
        //
        // The gap below is synthetic (a real handover lands within a few tens of
        // metres); it exists to put the first fix on B past START_WITNESS_ARC_M
        // on purpose.
        val zoneA = TRAKIYA_T10
        val zoneB = nextZoneFrom(zoneA, id = "trakiya-02-west", lengthM = 6_000.0)
        val det = ZoneDetector(listOf(zoneA, zoneB))

        val stepM = 36.0
        val speed = 130.0
        val stepMs = (stepM / (speed / 3.6) * 1000.0).toLong()
        val totalA = polylineLengthMeters(zoneA.centerline)
        val statesA = collectAlongCenterline(
            det, zoneA, fromArcM = -200.0, metres = totalA + 200.0,
            speedKmh = speed, stepM = stepM,
        )
        assertTrue(statesA.any { it is ZoneState.Exiting }, "Zone A must have exited")

        val lateArc = ZoneDetector.START_WITNESS_ARC_M * 1.5
        val statesB = collectAlongCenterline(
            det, zoneB, fromArcM = lateArc, metres = stepM * 2,
            speedKmh = speed, stepM = stepM,
            startTime = EPOCH_BASE + statesA.size * stepMs,
        )
        assertTrue(statesB.first() is ZoneState.InZone,
            "A handover must open B immediately and measured, got ${statesB.first()}")
        assertTrue(statesB.none { it is ZoneState.Unmeasured },
            "A handover is witnessed by construction — it must never yield Unmeasured")
    }

    @Test
    fun `the opposite-carriageway sibling cannot claim the co-located handover`() {
        // At a co-located camera the *westbound* sibling also starts within
        // COLOCATED_CAMERA_M of the eastbound zone's end — trakiya-03-west's
        // start is 15 m from trakiya-03-east's end, which is also
        // trakiya-04-east's start. Proximity alone therefore lets the sibling
        // claim the confirmation bypass, and a single wrong-bearing fix at the
        // seam is enough to open a *measured* traversal of the zone running back
        // the way we came — complete with an entry announcement.
        //
        // That wrong-bearing fix is not hypothetical: trakiya-04-east's stored
        // centerline opens with a 19 m segment bearing west (ISSUE-001), so a
        // route following the geometry genuinely reads as westbound for one fix.
        // Found by qa/colocated-zones.sh --all (7/24 pairs).
        val zoneA = TRAKIYA_T10
        val sibling = TRAKIYA_T10_OPPOSITE.copy(
            id = "trakiya-01-west-sibling",
            // Start it at A's end, running back the way A came.
            start = zoneA.end,
            end = zoneA.start,
            centerline = zoneA.centerline.reversed(),
        )
        val det = ZoneDetector(listOf(zoneA, sibling))

        val stepM = 36.0
        val speed = 130.0
        val stepMs = (stepM / (speed / 3.6) * 1000.0).toLong()
        val total = polylineLengthMeters(zoneA.centerline)
        val statesA = collectAlongCenterline(
            det, zoneA, fromArcM = -200.0, metres = total + 200.0,
            speedKmh = speed, stepM = stepM,
        )
        assertTrue(statesA.any { it is ZoneState.Exiting }, "Zone A must have exited")

        // One fix at the shared camera carrying the sibling's heading — the seam
        // artifact. It must NOT open a measured traversal of the sibling.
        val siblingStates = collectAlongCenterline(
            det, sibling, fromArcM = 0.0, metres = stepM,
            speedKmh = speed, stepM = stepM,
            startTime = EPOCH_BASE + statesA.size * stepMs,
        )
        assertTrue(
            siblingStates.none { it is ZoneState.InZone },
            "The opposite-carriageway sibling must not claim the handover bypass, got $siblingStates",
        )
    }

    @Test
    fun `a zone whose centerline starts with a backwards jog is still measurable`() {
        // The regression a 100 m START_WITNESS_ARC_M would have caused. On
        // i3-02-north, i6-01-east and trakiya-03-east the stored centerline opens
        // with a segment running ~180 degrees against the road (ISSUE-001), so an
        // honest approach projects onto the far end of that jog rather than to
        // arc 0. Measured across all 72 bundled zones, the worst first-match arc
        // on a legitimate approach is 121 m (2 s cadence) / 148 m (5 s cold-start
        // cadence) — both at i3-02-north, whose jog this fixture reproduces.
        //
        // If this test starts failing, START_WITNESS_ARC_M has been tightened
        // past what the shipped geometry supports and those zones will report
        // "not measured" on every real drive.
        val zone = jogStartZone(jogM = 121.0)
        val det = ZoneDetector(listOf(zone))

        // Approach from 250 m before the camera and carry on past confirmation.
        val trace = jogStartRoadTrace(
            fromM = -250.0,
            toM = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 2,
        )

        // Non-vacuity guard: the fixture has to actually exhibit the hazard. The
        // arc of the first fix that matches the zone at all is exactly what
        // decides provenance, so assert it sits in the danger band — past the
        // 100 m originally proposed, inside the 200 m actually chosen. Without
        // this the test would keep passing if the jog were ever flattened out.
        val firstMatchArc = trace.firstNotNullOfOrNull { p ->
            if (RoadMatcher.findMatchingZone(p, listOf(zone)) != null) {
                arcLengthOnPolyline(p.lat, p.lng, zone.centerline)
            } else {
                null
            }
        }
        assertTrue(firstMatchArc != null, "Fixture never matches the zone at all")
        assertTrue(firstMatchArc!! > 100.0,
            "Fixture no longer reproduces the ISSUE-001 jog — first matching fix " +
                "projects to arc $firstMatchArc, so a 100 m threshold would pass too " +
                "and this test proves nothing")
        assertTrue(firstMatchArc <= ZoneDetector.START_WITNESS_ARC_M,
            "First matching fix projects to arc $firstMatchArc, past " +
                "START_WITNESS_ARC_M (${ZoneDetector.START_WITNESS_ARC_M})")

        val states = trace.map { det.update(it) }

        assertTrue(states.any { it is ZoneState.InZone },
            "A genuine approach to a jog-start zone must still be measured, got $states")
        assertFalse(states.any { it is ZoneState.Unmeasured },
            "The backwards start jog must not be mistaken for a mid-zone join — " +
                "START_WITNESS_ARC_M (${ZoneDetector.START_WITNESS_ARC_M}) is too tight")
    }

    @Test
    fun `Unmeasured carries the zone and the road left, and nothing derived from timing`() {
        // What this state may show is the road's own facts: which zone it is (and
        // therefore its speed limit, the same thing the physical sign says) and
        // how much of it is left. There is deliberately no average, no
        // max-for-remainder and no elapsed time to render — that is structural,
        // enforced by the type rather than by convention.
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val startArc = 5_000.0
        val state = driveAlongCenterline(
            det, TRAKIYA_T10,
            fromArcM = startArc,
            metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 2,
        )

        val unmeasured = state as? ZoneState.Unmeasured
        assertTrue(unmeasured != null, "Expected Unmeasured, got $state")
        assertEquals(TRAKIYA_T10.id, unmeasured!!.zone.id)
        assertEquals(140, unmeasured.zone.speedLimits.car, "The limit must survive — it is a road fact")

        val total = polylineLengthMeters(TRAKIYA_T10.centerline)
        val expected = total - (startArc + ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 2)
        assertTrue(
            kotlin.math.abs(unmeasured.distanceRemaining - expected) < 100.0,
            "distanceRemaining should track the polyline arc to the end — " +
                "expected ~$expected, got ${unmeasured.distanceRemaining}",
        )
    }
}
