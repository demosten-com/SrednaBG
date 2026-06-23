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

class AverageSpeedCalcTest {

    @Test
    fun `normal driving under limit`() {
        // 10 km in 300 seconds, zone 19160m, limit 140 km/h
        val status = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 300_000L,
            stopDurationMs = 0L,
            distanceTraveled = 10_000.0,
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
        )

        // avgSpeed = 10000/300 * 3.6 = 120 km/h
        assertEquals(120.0, status.avgSpeed!!, 0.5)
        assertFalse(status.isOverLimit)
        assertEquals(9160.0, status.distanceRemaining, 1.0)
        assertTrue(status.timeRemaining > 0)
        assertTrue(status.maxSpeedForRemainder > 140) // Can go faster than limit for rest
    }

    @Test
    fun `speeding scenario`() {
        // 10 km in 240 seconds = 150 km/h average
        val status = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 240_000L,
            stopDurationMs = 0L,
            distanceTraveled = 10_000.0,
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
        )

        assertEquals(150.0, status.avgSpeed!!, 0.5)
        assertTrue(status.isOverLimit)
        // maxSpeedForRemainder should be less than limit (need to slow down)
        assertTrue(status.maxSpeedForRemainder < 140)
    }

    @Test
    fun `driving with stop deduction`() {
        // 10 km in 400 seconds total, 100 seconds stopped
        // Active time = 300 seconds -> same as normal driving
        val status = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 400_000L,
            stopDurationMs = 100_000L,
            distanceTraveled = 10_000.0,
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
        )

        // avgSpeed should be based on active time only: 10000/300 * 3.6 = 120 km/h
        assertEquals(120.0, status.avgSpeed!!, 0.5)
        assertFalse(status.isOverLimit)
    }

    @Test
    fun `time fully spent`() {
        // 15 km in 500 seconds at limit 140 km/h
        // Required time = 19160 / (140/3.6) = ~492.7 seconds
        // Time remaining = 492.7 - 500 = negative → clamped to MAX (250)
        val status = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 500_000L,
            stopDurationMs = 0L,
            distanceTraveled = 15_000.0,
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
        )

        assertTrue(status.timeRemaining < 0)
        assertEquals(250.0, status.maxSpeedForRemainder, 0.0)
        assertTrue(status.distanceRemaining > 0)
    }

    @Test
    fun `near zone end clamps remainder to 250`() {
        // Near the end of a short remaining slice, raw quotient would be > 6000 km/h.
        // 18 km traveled of 19.16 km zone in 492 seconds (limit 140 km/h →
        // required ≈ 492.7 s) leaves ~0.7 s of legal time for ~1160 m of road.
        val status = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 492_000L,
            stopDurationMs = 0L,
            distanceTraveled = 18_000.0,
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
        )

        assertTrue(status.timeRemaining > 0)
        assertTrue(status.distanceRemaining > 0)
        assertEquals(250.0, status.maxSpeedForRemainder, 0.0)
    }

    @Test
    fun `zero elapsed time edge case`() {
        val status = AverageSpeedCalc.calculate(
            entryTime = 1000L,
            currentTime = 1000L,
            stopDurationMs = 0L,
            distanceTraveled = 0.0,
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
        )

        assertNull(status.avgSpeed)
        assertFalse(status.isOverLimit)
        assertEquals(19_160.0, status.distanceRemaining, 1.0)
    }

    @Test
    fun `avg speed is null just below threshold and non-null at threshold`() {
        // Just under the 1.0s warm-up window — no meaningful sample yet.
        val warming = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 999L,
            stopDurationMs = 0L,
            distanceTraveled = 35.0,
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
        )
        assertNull(warming.avgSpeed)

        // At exactly 1.0s of active tracking — avg becomes available.
        val firstSample = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 1_000L,
            stopDurationMs = 0L,
            distanceTraveled = 36.0, // ~130 km/h for 1s
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
        )
        assertNotNull(firstSample.avgSpeed)
        assertEquals(129.6, firstSample.avgSpeed!!, 0.1)
    }

    @Test
    fun `distance already exceeded`() {
        val status = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 500_000L,
            stopDurationMs = 0L,
            distanceTraveled = 20_000.0,
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
        )

        assertEquals(0.0, status.distanceRemaining, 0.01)
        assertEquals(0.0, status.maxSpeedForRemainder, 0.01)
    }

    @Test
    fun `distance remaining override drives remainder instead of integrator`() {
        // The speed×time integrator has over-counted — distanceTraveled (20_000)
        // exceeds the zone (19_160), so the fallback `zoneDistance - distanceTraveled`
        // is negative → clamped to 0 → a collapsed 0 km/h remainder (see the
        // `distance already exceeded` test). The polyline-projection override says
        // 3_000 m of road actually remains.
        val status = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 300_000L,
            stopDurationMs = 0L,
            distanceTraveled = 20_000.0,
            zoneDistance = 19_160.0,
            speedLimitKmh = 140,
            distanceRemainingOverride = 3_000.0,
        )

        // Remainder follows the override, not the drifted integrator's clamped 0.
        assertEquals(3_000.0, status.distanceRemaining, 0.01)
        // With real road left and legal time still on the clock, max-for-remainder
        // is a usable positive number rather than the collapsed 0.
        assertTrue(status.timeRemaining > 0)
        assertTrue(status.maxSpeedForRemainder > 0)
    }

    @Test
    fun `national road lower speed limit`() {
        // I-4 zone with 90 km/h limit
        val status = AverageSpeedCalc.calculate(
            entryTime = 0L,
            currentTime = 200_000L,
            stopDurationMs = 0L,
            distanceTraveled = 5_000.0,
            zoneDistance = 9_200.0,
            speedLimitKmh = 90,
        )

        // avgSpeed = 5000/200 * 3.6 = 90 km/h exactly
        assertEquals(90.0, status.avgSpeed!!, 0.5)
        // At exactly the limit, isOverLimit should be false (not strictly over)
        assertFalse(status.isOverLimit)
    }
}
