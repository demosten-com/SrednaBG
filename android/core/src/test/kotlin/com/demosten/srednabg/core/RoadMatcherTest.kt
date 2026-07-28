// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class RoadMatcherTest {

    @Test
    fun `isOnRoad true for point on centerline`() {
        // Point exactly on Trakiya centerline
        val point = GpsPoint(
            lat = 42.480, lng = 23.800, speed = 130.0,
            timestamp = EPOCH_BASE, bearing = 310.0,
        )
        assertTrue(RoadMatcher.isOnRoad(point, TRAKIYA_T10))
    }

    @Test
    fun `isOnRoad true for point within 100m`() {
        // Offset ~50m north from a centerline point
        // At lat ~42.48, 50m north is roughly +0.00045 degrees latitude
        val point = GpsPoint(
            lat = 42.480 + 0.00045, lng = 23.800, speed = 130.0,
            timestamp = EPOCH_BASE, bearing = 310.0,
        )
        assertTrue(RoadMatcher.isOnRoad(point, TRAKIYA_T10))
    }

    @Test
    fun `isOnRoad false for distant point`() {
        // Point ~50 km away
        val point = GpsPoint(
            lat = 43.0, lng = 25.0, speed = 130.0,
            timestamp = EPOCH_BASE, bearing = 270.0,
        )
        assertFalse(RoadMatcher.isOnRoad(point, TRAKIYA_T10))
    }

    // A point sitting on the Trakiya centerline, plus the road's *local* heading
    // there — what matchDirection now compares against (not the zone's
    // end-to-end bearing).
    private val onRoadLat = 42.480
    private val onRoadLng = 23.800

    private fun localBearing(zone: Zone, lat: Double = onRoadLat, lng: Double = onRoadLng): Double =
        localPolylineBearing(
            zone.centerline,
            arcLengthOnPolyline(lat, lng, zone.centerline),
            RoadMatcher.LOCAL_BEARING_WINDOW_M,
        )!!

    private fun fixHeading(bearing: Double, lat: Double = onRoadLat, lng: Double = onRoadLng) =
        GpsPoint(lat = lat, lng = lng, speed = 130.0, timestamp = EPOCH_BASE, bearing = bearing)

    @Test
    fun `matchDirection accepts correct direction`() {
        assertTrue(RoadMatcher.matchDirection(fixHeading(localBearing(TRAKIYA_T10)), TRAKIYA_T10))
    }

    @Test
    fun `matchDirection rejects opposite direction`() {
        val opposite = (localBearing(TRAKIYA_T10) + 180) % 360
        assertFalse(RoadMatcher.matchDirection(fixHeading(opposite), TRAKIYA_T10))
    }

    @Test
    fun `matchDirection accepts within tolerance`() {
        // 40 degrees off should still be within 45 tolerance
        assertTrue(RoadMatcher.matchDirection(fixHeading(localBearing(TRAKIYA_T10) + 40), TRAKIYA_T10))
    }

    @Test
    fun `matchDirection uses the local heading, not the zone's end-to-end bearing`() {
        // The regression behind the phantom I-1 traversal: a course that sits
        // inside the tolerance of the zone's *end-to-end* bearing while running
        // across the road locally used to match. An L-shaped zone makes the two
        // readings disagree by construction — 2 km east, then 2 km north, so the
        // whole-line bearing is ~45° while the first leg runs due east.
        val corner = 42.0
        val lShaped = TRAKIYA_T10.copy(
            centerline = listOf(
                listOf(corner, 23.000),
                listOf(corner, 23.024),          // ~2 km east
                listOf(corner + 0.018, 23.024),  // ~2 km north
            ),
        )
        val overall = polylineBearing(lShaped.centerline)
        assertEquals(45.0, overall, 5.0)

        // A fix halfway along the eastbound leg, heading 30° — 15° off the zone's
        // end-to-end bearing (the old test would pass it) but 60° off the road it
        // is actually sitting on.
        val onEastLeg = fixHeading(30.0, lat = corner, lng = 23.012)
        assertEquals(90.0, localBearing(lShaped, corner, 23.012), 5.0)
        assertFalse(RoadMatcher.matchDirection(onEastLeg, lShaped))

        // …while a fix genuinely heading east there still matches.
        assertTrue(RoadMatcher.matchDirection(fixHeading(90.0, lat = corner, lng = 23.012), lShaped))
    }

    @Test
    fun `matchDirection fails gracefully on unknown direction string`() {
        // Degenerate centerline forces the cardinal-direction fallback; an
        // unknown direction string must mean "no match", not a crash — mirrors
        // the Swift port's matchDirectionFailsGracefullyOnUnknownDirectionString.
        val degenerate = TRAKIYA_T10.copy(
            direction = "northeast",
            centerline = listOf(listOf(42.427, 23.855)),
        )
        assertFalse(RoadMatcher.matchDirection(fixHeading(310.0), degenerate))
    }

    @Test
    fun `findMatchingZone returns correct zone`() {
        val allZones = listOf(TRAKIYA_T10, HEMUS_H12, I4_10)
        val bearing = polylineBearing(TRAKIYA_T10.centerline)
        val point = GpsPoint(
            lat = 42.480, lng = 23.800, speed = 130.0,
            timestamp = EPOCH_BASE, bearing = bearing,
        )
        val matched = RoadMatcher.findMatchingZone(point, allZones)
        assertNotNull(matched)
        assertEquals("trakiya-01-west", matched?.id)
    }

    @Test
    fun `findMatchingZone returns null when no match`() {
        val allZones = listOf(TRAKIYA_T10, HEMUS_H12, I4_10)
        // Point far from any zone
        val point = GpsPoint(
            lat = 44.0, lng = 26.0, speed = 100.0,
            timestamp = EPOCH_BASE, bearing = 90.0,
        )
        assertNull(RoadMatcher.findMatchingZone(point, allZones))
    }

    @Test
    fun `findMatchingZone rejects wrong direction`() {
        val allZones = listOf(TRAKIYA_T10) // only westbound
        val bearing = polylineBearing(TRAKIYA_T10.centerline)
        val oppositeBearing = (bearing + 180) % 360
        val point = GpsPoint(
            lat = 42.480, lng = 23.800, speed = 130.0,
            timestamp = EPOCH_BASE, bearing = oppositeBearing,
        )
        assertNull(RoadMatcher.findMatchingZone(point, allZones))
    }

    @Test
    fun `distanceToZoneStart`() {
        val point = GpsPoint(
            lat = 42.427, lng = 23.855, speed = 130.0,
            timestamp = EPOCH_BASE, bearing = 310.0,
        )
        val dist = RoadMatcher.distanceToZoneStart(point, TRAKIYA_T10)
        assertTrue(dist < 10) // Very close to start
    }

    @Test
    fun `distanceToZoneEnd`() {
        val point = GpsPoint(
            lat = 42.550, lng = 23.703, speed = 130.0,
            timestamp = EPOCH_BASE, bearing = 310.0,
        )
        val dist = RoadMatcher.distanceToZoneEnd(point, TRAKIYA_T10)
        assertTrue(dist < 10) // Very close to end
    }
}
