// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class HistoryStatsTest {

    // ---- sustainedExtremes ----

    @Test
    fun `empty series yields zero extremes`() {
        assertEquals(0.0 to 0.0, HistoryStats.sustainedExtremes(emptyList()))
    }

    @Test
    fun `single sample yields that sample as both extremes`() {
        val samples = listOf(SpeedSample(0, 88.0))
        assertEquals(88.0 to 88.0, HistoryStats.sustainedExtremes(samples))
    }

    @Test
    fun `constant series yields that constant for both extremes`() {
        val samples = (0..10).map { SpeedSample(it * 1000L, 120.0) }
        val (min, max) = HistoryStats.sustainedExtremes(samples)
        assertEquals(120.0, min, 1e-9)
        assertEquals(120.0, max, 1e-9)
    }

    @Test
    fun `a single-sample spike cannot become the sustained max`() {
        // 100 km/h steady with one 200 km/h fix. The 3 s moving average dilutes
        // the spike across its neighbours, so the smoothed max stays well under
        // 200 — "sustained for a few seconds, not a GPS flake".
        val samples = listOf(
            SpeedSample(0, 100.0),
            SpeedSample(1000, 100.0),
            SpeedSample(2000, 100.0),
            SpeedSample(3000, 200.0),
            SpeedSample(4000, 100.0),
            SpeedSample(5000, 100.0),
            SpeedSample(6000, 100.0),
        )
        val (min, max) = HistoryStats.sustainedExtremes(samples)
        assertEquals(100.0, min, 1e-9)
        assertTrue(max < 150.0, "spike-driven max should be smoothed down, was $max")
    }

    @Test
    fun `a single-sample drop cannot become the sustained min`() {
        val samples = listOf(
            SpeedSample(0, 120.0),
            SpeedSample(1000, 120.0),
            SpeedSample(2000, 120.0),
            SpeedSample(3000, 0.0),
            SpeedSample(4000, 120.0),
            SpeedSample(5000, 120.0),
            SpeedSample(6000, 120.0),
        )
        val (min, max) = HistoryStats.sustainedExtremes(samples)
        assertEquals(120.0, max, 1e-9)
        assertTrue(min > 60.0, "drop-driven min should be smoothed up, was $min")
    }

    @Test
    fun `a sustained climb is reflected in the max`() {
        // Ten seconds at 160 after ten at 90 — the high is genuinely sustained,
        // so the smoothed max should sit close to 160.
        val low = (0..9).map { SpeedSample(it * 1000L, 90.0) }
        val high = (10..19).map { SpeedSample(it * 1000L, 160.0) }
        val (min, max) = HistoryStats.sustainedExtremes(low + high)
        assertEquals(90.0, min, 1e-6)
        assertEquals(160.0, max, 1e-6)
    }

    @Test
    fun `sustainedExtremes matches the shared spike fixture`() {
        val fx = loadFixture("history/spike_suppressed.json")
        val (min, max) = HistoryStats.sustainedExtremes(
            fx.samples.map { SpeedSample(it.timestampMs, it.speedKmh) },
            fx.windowMs,
        )
        assertEquals(fx.expectedSustainedMin, min, 0.01)
        assertEquals(fx.expectedSustainedMax, max, 0.01)
    }

    // ---- runningAverage ----

    @Test
    fun `runningAverage of empty is empty`() {
        assertTrue(HistoryStats.runningAverage(emptyList()).isEmpty())
    }

    @Test
    fun `runningAverage of a constant series is that constant throughout`() {
        val samples = (0..5).map { SpeedSample(it * 1000L, 100.0) }
        val avg = HistoryStats.runningAverage(samples)
        assertEquals(samples.size, avg.size)
        assertTrue(avg.all { kotlin.math.abs(it.speedKmh - 100.0) < 1e-9 })
    }

    @Test
    fun `runningAverage starts at the first speed and converges to the trip average`() {
        // Steps: 60, then five at 120. The running average must start at 60 and
        // climb toward — but stay under — 120 (it can never overshoot the max).
        val samples = listOf(
            SpeedSample(0, 60.0),
            SpeedSample(1000, 120.0),
            SpeedSample(2000, 120.0),
            SpeedSample(3000, 120.0),
            SpeedSample(4000, 120.0),
            SpeedSample(5000, 120.0),
        )
        val avg = HistoryStats.runningAverage(samples)
        assertEquals(60.0, avg.first().speedKmh, 1e-9)
        assertTrue(avg.zipWithNext().all { (a, b) -> b.speedKmh >= a.speedKmh }, "should be monotonically rising")
        assertTrue(avg.last().speedKmh in 100.0..120.0, "final was ${avg.last().speedKmh}")
        // Timestamps are preserved 1:1.
        assertEquals(samples.map { it.timestampMs }, avg.map { it.timestampMs })
    }

    @Test
    fun `runningAverage is smoother than the raw series`() {
        // A fluctuating series: the running average's spread must be much smaller
        // than the raw speed spread — i.e. it is NOT a copy of the speed curve,
        // and (crucially) NOT flat either.
        val raw = listOf(70.0, 140.0, 60.0, 150.0, 80.0, 130.0)
        val samples = raw.mapIndexed { i, v -> SpeedSample(i * 1000L, v) }
        val avg = HistoryStats.runningAverage(samples).map { it.speedKmh }
        val rawSpread = raw.max() - raw.min()
        val avgSpread = avg.max() - avg.min()
        assertTrue(avgSpread < rawSpread, "avg spread $avgSpread should be < raw spread $rawSpread")
        assertTrue(avgSpread > 0.0, "running average must not be flat for a fluctuating series")
    }

    // ---- downsample ----

    @Test
    fun `downsample passes through a short series unchanged`() {
        val samples = (0..9).map { SpeedSample(it * 1000L, it.toDouble()) }
        assertEquals(samples, HistoryStats.downsample(samples, maxPoints = 500))
    }

    @Test
    fun `downsample passes through exactly-maxPoints unchanged`() {
        val samples = (0 until 500).map { SpeedSample(it * 1000L, it.toDouble()) }
        assertEquals(samples, HistoryStats.downsample(samples, maxPoints = 500))
    }

    @Test
    fun `downsample caps a long series at maxPoints`() {
        val samples = (0 until 5000).map { SpeedSample(it * 1000L, it.toDouble()) }
        val out = HistoryStats.downsample(samples, maxPoints = 500)
        assertEquals(500, out.size)
        // Timestamps stay monotonically increasing and span the original range.
        assertTrue(out.zipWithNext().all { (a, b) -> a.timestampMs < b.timestampMs })
        assertTrue(out.first().timestampMs >= samples.first().timestampMs)
        assertTrue(out.last().timestampMs <= samples.last().timestampMs)
    }

    @Test
    fun `downsample preserves the average speed of a ramp`() {
        val samples = (0 until 2000).map { SpeedSample(it * 1000L, it.toDouble()) }
        val out = HistoryStats.downsample(samples, maxPoints = 500)
        val srcAvg = samples.map { it.speedKmh }.average()
        val outAvg = out.map { it.speedKmh }.average()
        assertEquals(srcAvg, outAvg, 1.0)
    }

    @Test
    fun `downsample rejects a non-positive cap`() {
        val samples = listOf(SpeedSample(0, 1.0), SpeedSample(1, 2.0))
        org.junit.jupiter.api.assertThrows<IllegalArgumentException> {
            HistoryStats.downsample(samples, maxPoints = 0)
        }
    }

    // ---- fixture loading ----

    @Serializable
    private data class FixtureSample(val timestampMs: Long, val speedKmh: Double)

    @Serializable
    private data class Fixture(
        val windowMs: Long,
        val samples: List<FixtureSample>,
        val expectedSustainedMin: Double,
        val expectedSustainedMax: Double,
    )

    private val json = Json { ignoreUnknownKeys = true }

    private fun loadFixture(path: String): Fixture {
        val text = requireNotNull(javaClass.classLoader?.getResourceAsStream(path)) {
            "fixture not found on test classpath: $path"
        }.bufferedReader().use { it.readText() }
        return json.decodeFromString(Fixture.serializer(), text)
    }
}
