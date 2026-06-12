// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

class GeoUtilsTest {

    @Test
    fun `haversine same point is zero`() {
        assertEquals(0.0, haversineDistance(42.5, 23.8, 42.5, 23.8), 0.01)
    }

    @Test
    fun `haversine sofia to plovdiv`() {
        // Sofia (42.6977, 23.3219) to Plovdiv (42.1354, 24.7453) ~ 130 km
        val dist = haversineDistance(42.6977, 23.3219, 42.1354, 24.7453)
        assertEquals(130_000.0, dist, 5_000.0) // within 5 km
    }

    @Test
    fun `haversine sofia to burgas`() {
        // Sofia to Burgas ~ 340 km (straight line)
        val dist = haversineDistance(42.6977, 23.3219, 42.5048, 27.4626)
        assertEquals(340_000.0, dist, 20_000.0) // within 20 km
    }

    @Test
    fun `haversine one degree latitude at equator`() {
        // 1 degree latitude ~ 111,195 m
        val dist = haversineDistance(0.0, 0.0, 1.0, 0.0)
        assertEquals(111_195.0, dist, 200.0)
    }

    @Test
    fun `point to segment distance on segment`() {
        // Point on the segment itself -> distance ~0
        val dist = pointToSegmentDistance(42.450, 23.830, 42.427, 23.855, 42.550, 23.703)
        assertTrue(dist < 500) // Point approximately on the Trakiya centerline
    }

    @Test
    fun `point to segment distance at vertex`() {
        // Point exactly at vertex A
        val dist = pointToSegmentDistance(42.427, 23.855, 42.427, 23.855, 42.550, 23.703)
        assertEquals(0.0, dist, 1.0)
    }

    @Test
    fun `point to segment distance far away`() {
        // Point far from segment
        val dist = pointToSegmentDistance(43.0, 25.0, 42.427, 23.855, 42.550, 23.703)
        assertTrue(dist > 50_000) // > 50 km away
    }

    @Test
    fun `point to polyline distance on centerline`() {
        val dist = pointToPolylineDistance(42.480, 23.800, TRAKIYA_T10.centerline)
        assertTrue(dist < 50) // Very close to a centerline point
    }

    @Test
    fun `point to polyline distance empty polyline`() {
        assertEquals(Double.MAX_VALUE, pointToPolylineDistance(42.5, 23.8, emptyList()))
    }

    @Test
    fun `point to polyline distance single point`() {
        val poly = listOf(listOf(42.5, 23.8))
        val dist = pointToPolylineDistance(42.5, 23.801, poly)
        assertTrue(dist < 100) // Very close
    }

    @Test
    fun `project onto polyline at start`() {
        val proj = projectOntoPolyline(42.427, 23.855, TRAKIYA_T10.centerline)
        assertTrue(proj < 100) // Should be near 0 (start of polyline)
    }

    @Test
    fun `project onto polyline at end`() {
        val proj = projectOntoPolyline(42.550, 23.703, TRAKIYA_T10.centerline)
        val totalLength = computePolylineLength(TRAKIYA_T10.centerline)
        assertEquals(totalLength, proj, totalLength * 0.05) // Within 5% of total length
    }

    @Test
    fun `project onto polyline at midpoint`() {
        // Use the middle point of the centerline
        val mid = TRAKIYA_T10.centerline[3] // [42.510, 23.770]
        val proj = projectOntoPolyline(mid[0], mid[1], TRAKIYA_T10.centerline)
        val totalLength = computePolylineLength(TRAKIYA_T10.centerline)
        assertTrue(proj > totalLength * 0.3)
        assertTrue(proj < totalLength * 0.7)
    }

    @Test
    fun `project point onto polyline returns null for empty polyline`() {
        assertNull(projectPointOntoPolyline(42.5, 23.8, emptyList()))
    }

    @Test
    fun `project point onto polyline returns null for single-point polyline`() {
        assertNull(projectPointOntoPolyline(42.5, 23.8, listOf(listOf(42.5, 23.8))))
    }

    @Test
    fun `project point onto polyline at vertex returns same coords`() {
        val polyline = listOf(listOf(42.0, 23.0), listOf(42.0, 24.0))
        val proj = projectPointOntoPolyline(42.0, 23.0, polyline)!!
        assertEquals(42.0, proj.lat, 1e-6)
        assertEquals(23.0, proj.lng, 1e-6)
        assertTrue(proj.distanceFromLineM < 1.0)
        assertEquals(90.0, proj.bearing, 1.0) // segment heads due east
    }

    @Test
    fun `project point onto polyline perpendicular to mid-segment`() {
        // Segment along latitude 42.0 from lng 23.0 to 24.0; point sits north of midpoint.
        val polyline = listOf(listOf(42.0, 23.0), listOf(42.0, 24.0))
        val proj = projectPointOntoPolyline(42.001, 23.5, polyline)!!
        assertEquals(42.0, proj.lat, 1e-4)
        assertEquals(23.5, proj.lng, 1e-4)
        // ~0.001 deg latitude ≈ 111 m perpendicular distance
        assertEquals(111.0, proj.distanceFromLineM, 5.0)
        assertEquals(90.0, proj.bearing, 1.0)
    }

    @Test
    fun `project point onto polyline past last vertex clamps to end`() {
        val polyline = listOf(listOf(42.0, 23.0), listOf(42.0, 24.0))
        val proj = projectPointOntoPolyline(42.0, 25.0, polyline)!!
        assertEquals(42.0, proj.lat, 1e-6)
        assertEquals(24.0, proj.lng, 1e-6)
    }

    @Test
    fun `project point onto polyline picks nearest segment`() {
        // Two-segment polyline: east leg, then south leg. Point is far east of the south leg.
        val polyline = listOf(
            listOf(42.0, 23.0),
            listOf(42.0, 24.0),
            listOf(41.0, 24.0),
        )
        val proj = projectPointOntoPolyline(41.5, 24.5, polyline)!!
        // Should snap onto the south leg, near (41.5, 24.0)
        assertEquals(41.5, proj.lat, 1e-3)
        assertEquals(24.0, proj.lng, 1e-3)
        assertEquals(180.0, proj.bearing, 1.0) // south leg heads due south
    }

    @Test
    fun `bearing due east`() {
        val b = bearingBetween(42.0, 23.0, 42.0, 24.0)
        assertEquals(90.0, b, 1.0)
    }

    @Test
    fun `bearing due north`() {
        val b = bearingBetween(42.0, 23.0, 43.0, 23.0)
        assertEquals(0.0, b, 1.0)
    }

    @Test
    fun `bearing due south`() {
        val b = bearingBetween(43.0, 23.0, 42.0, 23.0)
        assertEquals(180.0, b, 1.0)
    }

    @Test
    fun `bearing due west`() {
        val b = bearingBetween(42.0, 24.0, 42.0, 23.0)
        assertEquals(270.0, b, 1.0)
    }

    @Test
    fun `bearing difference zero`() {
        assertEquals(0.0, bearingDifference(90.0, 90.0), 0.01)
    }

    @Test
    fun `bearing difference wrap around`() {
        assertEquals(20.0, bearingDifference(10.0, 350.0), 0.01)
    }

    @Test
    fun `bearing difference opposite`() {
        assertEquals(180.0, bearingDifference(0.0, 180.0), 0.01)
    }

    @Test
    fun `bearing difference symmetric`() {
        assertEquals(bearingDifference(30.0, 60.0), bearingDifference(60.0, 30.0), 0.01)
    }

    @Test
    fun `direction to bearing all cardinals`() {
        assertEquals(0.0, directionToBearing("north"))
        assertEquals(90.0, directionToBearing("east"))
        assertEquals(180.0, directionToBearing("south"))
        assertEquals(270.0, directionToBearing("west"))
    }

    @Test
    fun `direction to bearing unknown returns null`() {
        assertNull(directionToBearing("northeast"))
    }

    @Test
    fun `polyline bearing trakiya`() {
        // Trakiya t10 goes from [42.427, 23.855] to [42.550, 23.703]
        // Latitude increases (north), longitude decreases (west) -> NW bearing ~300-330
        val bearing = polylineBearing(TRAKIYA_T10.centerline)
        assertTrue(bearing > 290 && bearing < 340, "Bearing should be NW, got $bearing")
    }

    @Test
    fun `polyline bearing hemus`() {
        // Hemus h12: [42.725, 23.528] -> [42.779, 23.736]
        // Lat increases (N), Lng increases (E) -> NE bearing ~60-80
        val bearing = polylineBearing(HEMUS_H12.centerline)
        assertTrue(bearing > 50 && bearing < 90, "Bearing should be NE, got $bearing")
    }

    @Test
    fun `polyline bearing too short throws`() {
        assertThrows<IllegalArgumentException> { polylineBearing(listOf(listOf(42.0, 23.0))) }
    }

    private fun computePolylineLength(polyline: List<List<Double>>): Double {
        var total = 0.0
        for (i in 0 until polyline.size - 1) {
            total += haversineDistance(polyline[i][0], polyline[i][1], polyline[i + 1][0], polyline[i + 1][1])
        }
        return total
    }
}
