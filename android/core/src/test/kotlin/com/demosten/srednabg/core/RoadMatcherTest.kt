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

    @Test
    fun `matchDirection accepts correct direction`() {
        // Trakiya t10 polyline bearing is ~310-320 degrees (NW)
        val polyBearing = polylineBearing(TRAKIYA_T10.centerline)
        assertTrue(RoadMatcher.matchDirection(polyBearing, TRAKIYA_T10))
    }

    @Test
    fun `matchDirection rejects opposite direction`() {
        // Opposite of NW (~310) is SE (~130)
        val polyBearing = polylineBearing(TRAKIYA_T10.centerline)
        val opposite = (polyBearing + 180) % 360
        assertFalse(RoadMatcher.matchDirection(opposite, TRAKIYA_T10))
    }

    @Test
    fun `matchDirection accepts within tolerance`() {
        val polyBearing = polylineBearing(TRAKIYA_T10.centerline)
        // 40 degrees off should still be within 45 tolerance
        assertTrue(RoadMatcher.matchDirection(polyBearing + 40, TRAKIYA_T10))
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
