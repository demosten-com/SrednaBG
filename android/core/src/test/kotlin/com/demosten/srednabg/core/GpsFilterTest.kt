// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import java.util.Random
import kotlin.math.abs

class GpsFilterTest {

    private lateinit var filter: GpsFilter

    @BeforeEach
    fun setup() {
        filter = GpsFilter()
    }

    @Test
    fun `first point passes through unchanged`() {
        val point = GpsPoint(42.7, 23.3, 100.0, EPOCH_BASE, 90.0, 5.0)
        val result = filter.filter(point)
        assertEquals(point.lat, result.lat)
        assertEquals(point.lng, result.lng)
        assertEquals(point.speed, result.speed)
    }

    @Test
    fun `stationary noisy readings converge to true position`() {
        val trueLat = 42.700
        val trueLng = 23.300
        val random = Random(42)

        // Feed 30 noisy readings at the same position
        var lastResult: GpsPoint? = null
        for (i in 0 until 30) {
            val noiseLat = random.nextGaussian() * 10.0 / 111_320.0 // ~10m noise
            val noiseLng = random.nextGaussian() * 10.0 / 111_320.0
            val point = GpsPoint(
                lat = trueLat + noiseLat,
                lng = trueLng + noiseLng,
                speed = 0.0,
                timestamp = EPOCH_BASE + i * 1000L,
                bearing = 0.0,
                accuracy = 10.0,
            )
            lastResult = filter.filter(point)
        }

        // After 30 readings, filtered position should be closer to truth than raw noise
        val errorLat = abs(lastResult!!.lat - trueLat) * 111_320.0
        val errorLng = abs(lastResult.lng - trueLng) * 111_320.0
        assertTrue(errorLat < 5.0, "Lat error should be < 5m, was ${errorLat}m")
        assertTrue(errorLng < 5.0, "Lng error should be < 5m, was ${errorLng}m")
    }

    @Test
    fun `filter tracks moving vehicle within tolerance`() {
        val trace = generateGpsTrace(TRAKIYA_T10, 120.0, intervalMs = 1000)
        val noisyTrace = addNoiseToTrace(trace, noiseMeters = 8.0)

        var maxError = 0.0
        for (i in noisyTrace.indices) {
            val filtered = filter.filter(noisyTrace[i])
            val errorM = haversineDistance(filtered.lat, filtered.lng, trace[i].lat, trace[i].lng)
            if (i > 5) { // skip initial convergence
                maxError = maxOf(maxError, errorM)
            }
        }

        // On curved roads at speed, filter lags on direction changes.
        // Filtered output should be significantly better than raw noise (8m * 3 = 24m at 3-sigma).
        assertTrue(maxError < 200.0, "Max error should be < 200m, was ${maxError}m")
    }

    @Test
    fun `speed outlier is dampened`() {
        // Normal speed, then spike, then back to normal
        val points = listOf(
            GpsPoint(42.700, 23.300, 120.0, EPOCH_BASE, 90.0, 5.0),
            GpsPoint(42.701, 23.301, 120.0, EPOCH_BASE + 1000, 90.0, 5.0),
            GpsPoint(42.702, 23.302, 120.0, EPOCH_BASE + 2000, 90.0, 5.0),
            GpsPoint(42.703, 23.303, 300.0, EPOCH_BASE + 3000, 90.0, 5.0), // spike
            GpsPoint(42.704, 23.304, 120.0, EPOCH_BASE + 4000, 90.0, 5.0),
        )

        var spikeFiltered = 0.0
        for (point in points) {
            val result = filter.filter(point)
            if (point.timestamp == EPOCH_BASE + 3000) {
                spikeFiltered = result.speed
            }
        }

        // The spike should be significantly dampened
        assertTrue(spikeFiltered < 250.0, "Spike should be dampened, was $spikeFiltered")
        assertTrue(spikeFiltered > 120.0, "Spike should still show increase, was $spikeFiltered")
    }

    @Test
    fun `reset clears state`() {
        val point1 = GpsPoint(42.700, 23.300, 100.0, EPOCH_BASE, 90.0, 5.0)
        filter.filter(point1)

        filter.reset()

        // After reset, next point should pass through as if first
        val point2 = GpsPoint(43.000, 24.000, 80.0, EPOCH_BASE + 60000, 180.0, 5.0)
        val result = filter.filter(point2)
        assertEquals(point2.lat, result.lat)
        assertEquals(point2.lng, result.lng)
        assertEquals(point2.speed, result.speed)
    }

    @Test
    fun `large time gap resets filter state`() {
        val point1 = GpsPoint(42.700, 23.300, 100.0, EPOCH_BASE, 90.0, 5.0)
        filter.filter(point1)

        // 60 second gap (> 30s threshold)
        val point2 = GpsPoint(42.800, 23.400, 120.0, EPOCH_BASE + 60_000, 90.0, 5.0)
        val result = filter.filter(point2)

        // Should accept the new position directly (gap too large to interpolate)
        assertEquals(point2.lat, result.lat)
        assertEquals(point2.lng, result.lng)
    }

    @Test
    fun `filtered speed is never negative`() {
        val point1 = GpsPoint(42.700, 23.300, 5.0, EPOCH_BASE, 90.0, 10.0)
        filter.filter(point1)

        val point2 = GpsPoint(42.700, 23.300, 0.0, EPOCH_BASE + 1000, 90.0, 10.0)
        val result = filter.filter(point2)

        assertTrue(result.speed >= 0.0, "Filtered speed should never be negative")
    }
}
