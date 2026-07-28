// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * Tests for the fixture helpers themselves.
 *
 * [pointOnApproach] decides where every "a car genuinely driving this zone"
 * trace begins, so the entry-provenance suite's verdicts rest on it: if it
 * silently stopped extrapolating *backwards* down the approach road, those
 * tests would keep passing while asserting something else entirely (a drive
 * that starts at arc 0 is witnessed either way). Assert it directly rather than
 * only through [collectAlongCenterline].
 *
 * Mirrored by Swift `TestFixturesTests`.
 */
class TestFixturesTest {

    @Test
    fun `pointOnApproach places a negative arc behind the zone start, on the approach road`() {
        val zone = TRAKIYA_T10
        val heading = localPolylineBearing(
            zone.centerline, 0.0, RoadMatcher.LOCAL_BEARING_WINDOW_M,
        )!!
        val v0 = zone.centerline.first()

        val at = pointOnApproach(zone, -100.0, heading)

        // 100 m from the first vertex…
        assertEquals(
            100.0,
            haversineDistance(at[0], at[1], v0[0], v0[1]),
            1.0,
            "A -100 m arc must sit 100 m from the centerline start",
        )
        // …on the far side of it, i.e. the bearing from there to the start is the
        // direction of travel, not its reverse.
        assertEquals(
            0.0,
            bearingDifference(bearingBetween(at[0], at[1], v0[0], v0[1]), heading),
            1.0,
            "The approach point must lie behind the start, heading into the zone",
        )
        // And the projection of an approach point onto the centerline clamps to
        // arc 0 — the property entry provenance is built on.
        assertEquals(
            0.0,
            arcLengthOnPolyline(at[0], at[1], zone.centerline),
            0.5,
            "An approach point must project to arc ~0",
        )
    }

    @Test
    fun `pointOnApproach defers to pointAtArcLength for non-negative arcs`() {
        val zone = TRAKIYA_T10
        val heading = polylineBearing(zone.centerline)
        for (arc in listOf(0.0, 250.0, 5_000.0)) {
            assertEquals(
                pointAtArcLength(zone.centerline, arc),
                pointOnApproach(zone, arc, heading),
                "Arc $arc is on the line, so it must come straight from pointAtArcLength",
            )
        }
    }

    @Test
    fun `pointOnApproach extrapolates from the stored first vertex, jog and all`() {
        // For the ISSUE-001 fixture the stored first vertex IS the camera, while
        // the geometry immediately doubles back. An approach point must still be
        // measured off that vertex along the real road heading — this is what
        // makes the jog reachable at an arc inside the 100–200 m danger band.
        val zone = jogStartZone()
        val v0 = zone.centerline.first()

        val at = pointOnApproach(zone, -200.0, JOG_ZONE_HEADING_DEG)

        assertEquals(
            200.0,
            haversineDistance(at[0], at[1], v0[0], v0[1]),
            1.0,
            "A -200 m arc must sit 200 m behind the jog zone's camera",
        )
        // And it must project onto the *jog* vertex rather than clamping to arc 0
        // — the whole point of the fixture, and the reason a legitimate approach
        // to i3-02-north lands inside the 100–200 m danger band instead of at 0.
        assertEquals(
            121.0,
            arcLengthOnPolyline(at[0], at[1], zone.centerline),
            2.0,
            "An approach point must snap to the far end of the backwards jog",
        )
    }

    @Test
    fun `jogStartZone centerline ends exactly at the zone end`() {
        val zone = jogStartZone()
        val last = zone.centerline.last()
        assertEquals(
            0.0,
            haversineDistance(last[0], last[1], zone.end.lat, zone.end.lng),
            1.0,
            "centerline.last() and zone.end must agree, or remaining-distance " +
                "assertions measure a different road than the endpoint checks",
        )
    }
}
