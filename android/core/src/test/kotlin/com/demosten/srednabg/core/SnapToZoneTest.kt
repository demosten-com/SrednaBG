// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertSame
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class SnapToZoneTest {

    private val rawPoint = GpsPoint(
        lat = 42.5,
        lng = 23.8,
        speed = 130.0,
        timestamp = 1_700_000_000_000L,
        bearing = 270.0,
        accuracy = 5.0,
    )

    @Test
    fun `null position returns null`() {
        assertNull(snapToZone(null, ZoneState.Outside))
    }

    @Test
    fun `outside state returns raw position unchanged`() {
        val snapped = snapToZone(rawPoint, ZoneState.Outside)
        assertSame(rawPoint, snapped)
    }

    @Test
    fun `exiting state returns raw position unchanged`() {
        val state = ZoneState.Exiting(zone = TRAKIYA_T10, finalAvgSpeed = 130.0)
        val snapped = snapToZone(rawPoint, state)
        assertSame(rawPoint, snapped)
    }

    @Test
    fun `in-zone state snaps lat lng to centerline and overwrites bearing`() {
        // Start of Trakiya t10 centerline is approximately [42.427, 23.855]; nudge the
        // raw point a little perpendicular to the road so we can observe the snap.
        val nearStartRaw = rawPoint.copy(lat = 42.428, lng = 23.860, bearing = 12.0)
        val state = ZoneState.InZone(
            zone = TRAKIYA_T10,
            entryTime = nearStartRaw.timestamp,
            distanceTraveled = 0.0,
            speedStatus = SpeedStatus(
                avgSpeed = null,
                maxSpeedForRemainder = 140.0,
                distanceRemaining = TRAKIYA_T10.distanceM.toDouble(),
                timeRemaining = 0.0,
                isOverLimit = false,
            ),
            distanceRemaining = TRAKIYA_T10.distanceM.toDouble(),
        )

        val snapped = snapToZone(nearStartRaw, state)
        assertNotNull(snapped)
        snapped!!

        // Snapped lat/lng should sit on the centerline (well within 50 m of the raw
        // point — the perpendicular delta is tiny at this offset).
        val distFromRaw = haversineDistance(snapped.lat, snapped.lng, nearStartRaw.lat, nearStartRaw.lng)
        assertTrue(distFromRaw < 600.0, "Snap should be modest, got ${distFromRaw}m")
        val distFromLine = pointToPolylineDistance(snapped.lat, snapped.lng, TRAKIYA_T10.centerline)
        assertTrue(distFromLine < 1.0, "Snapped point should lie on centerline, got ${distFromLine}m")

        // Bearing should be overwritten with the segment bearing (Trakiya t10 heads NW).
        assertTrue(snapped.bearing in 290.0..340.0, "Expected NW bearing, got ${snapped.bearing}")

        // Non-positional fields are preserved.
        assertEquals(nearStartRaw.speed, snapped.speed)
        assertEquals(nearStartRaw.timestamp, snapped.timestamp)
        assertEquals(nearStartRaw.accuracy, snapped.accuracy)
    }

    @Test
    fun `in-zone state with degenerate centerline returns raw position`() {
        val degenerateZone = TRAKIYA_T10.copy(centerline = listOf(listOf(42.5, 23.8)))
        val state = ZoneState.InZone(
            zone = degenerateZone,
            entryTime = rawPoint.timestamp,
            distanceTraveled = 0.0,
            speedStatus = SpeedStatus(null, 140.0, 0.0, 0.0, false),
            distanceRemaining = 0.0,
        )
        val snapped = snapToZone(rawPoint, state)
        assertSame(rawPoint, snapped)
    }
}
