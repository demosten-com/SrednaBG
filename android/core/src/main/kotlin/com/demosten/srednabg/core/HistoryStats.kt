// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

/**
 * A single speed-over-time reading captured during a zone traversal. The app
 * layer appends one per accepted GPS fix while [ZoneState.InZone]; the finalized
 * series is stored with the history record and drawn on the detail graph.
 *
 * Mirrors the Swift `SpeedSample` in the iOS `SrednaBGCore` port — keep the two
 * in sync (same fields, same [sustainedExtremes] / [downsample] semantics, same
 * shared JSON fixtures under `src/test/resources/`).
 *
 * @property timestampMs fix time as epoch **milliseconds**.
 * @property speedKmh ground speed in **km/h**.
 */
data class SpeedSample(
    val timestampMs: Long,
    val speedKmh: Double,
)

/**
 * Pure statistics over a captured [SpeedSample] series. No Android or engine
 * dependencies so it unit-tests on the JVM and hand-ports 1:1 to Swift.
 */
object HistoryStats {

    /** Default smoothing window for [sustainedExtremes], in milliseconds. */
    const val DEFAULT_WINDOW_MS: Long = 3000L

    /** Default cap for [downsample]. */
    const val DEFAULT_MAX_POINTS: Int = 500

    /**
     * Sustained min/max speed over the series.
     *
     * A raw min/max would report a single-sample GPS spike or drop as the
     * extreme — "top speed 231" from one bad fix. Instead we first smooth the
     * series with a centered moving-average window ([windowMs], default 3 s):
     * each point becomes the mean of the samples within ±[windowMs]/2 of it, so
     * a lone outlier is diluted by its neighbours and can't dominate. The
     * extremes of the *smoothed* series are what a driver actually sustained for
     * a few seconds.
     *
     * @return `(sustainedMin, sustainedMax)` in km/h. `(0.0, 0.0)` for an empty
     *   series; `(speed, speed)` for a single sample.
     */
    fun sustainedExtremes(
        samples: List<SpeedSample>,
        windowMs: Long = DEFAULT_WINDOW_MS,
    ): Pair<Double, Double> {
        if (samples.isEmpty()) return 0.0 to 0.0
        if (samples.size == 1) return samples[0].speedKmh to samples[0].speedKmh

        val sorted = samples.sortedBy { it.timestampMs }
        val half = windowMs / 2
        var min = Double.MAX_VALUE
        var max = -Double.MAX_VALUE
        // Two-pointer sliding window over the time-sorted series: [lo, hi) is the
        // set of samples within ±half of sorted[i]. Both pointers advance
        // monotonically, so this is O(n) rather than O(n·window).
        var lo = 0
        var hi = 0
        for (i in sorted.indices) {
            val t = sorted[i].timestampMs
            while (lo < sorted.size && sorted[lo].timestampMs < t - half) lo++
            if (hi < lo) hi = lo
            while (hi < sorted.size && sorted[hi].timestampMs <= t + half) hi++
            var sum = 0.0
            for (j in lo until hi) sum += sorted[j].speedKmh
            val smoothed = sum / (hi - lo)
            if (smoothed < min) min = smoothed
            if (smoothed > max) max = smoothed
        }
        return min to max
    }

    /**
     * The **running** (cumulative) average speed at each sample — the metric this
     * app is actually about. Point `i` is the time-weighted mean speed over
     * `[t0, t_i]` (trapezoidal integral of speed over elapsed time), so the series
     * starts at the first sample's speed and converges toward the final trip
     * average. Plotted as the graph's average line, it evolves with the drive
     * instead of being a flat final-average reference.
     *
     * @return one [SpeedSample] per input (same timestamps), `speedKmh` holding
     *   the running average up to and including that point. Empty in, empty out.
     */
    fun runningAverage(samples: List<SpeedSample>): List<SpeedSample> {
        if (samples.isEmpty()) return emptyList()
        val sorted = samples.sortedBy { it.timestampMs }
        val t0 = sorted.first().timestampMs
        val out = ArrayList<SpeedSample>(sorted.size)
        out.add(SpeedSample(sorted[0].timestampMs, sorted[0].speedKmh))
        var integral = 0.0 // km/h · ms
        for (i in 1 until sorted.size) {
            val dt = (sorted[i].timestampMs - sorted[i - 1].timestampMs).toDouble()
            integral += (sorted[i - 1].speedKmh + sorted[i].speedKmh) / 2.0 * dt
            val elapsed = (sorted[i].timestampMs - t0).toDouble()
            val avg = if (elapsed > 0.0) integral / elapsed else sorted[i].speedKmh
            out.add(SpeedSample(sorted[i].timestampMs, avg))
        }
        return out
    }

    /**
     * Downsample to at most [maxPoints] samples for storage / plotting.
     *
     * Pass-through when the series already fits (a short zone at 1 Hz stays
     * intact). Otherwise the series is split into [maxPoints] contiguous buckets
     * and each collapses to one sample whose timestamp and speed are the bucket
     * mean — preserving the overall shape without unbounded storage (the longest
     * zones at 1 Hz run well past 500 samples).
     */
    fun downsample(
        samples: List<SpeedSample>,
        maxPoints: Int = DEFAULT_MAX_POINTS,
    ): List<SpeedSample> {
        require(maxPoints > 0) { "maxPoints must be positive" }
        if (samples.size <= maxPoints) return samples
        val sorted = samples.sortedBy { it.timestampMs }
        val n = sorted.size
        val out = ArrayList<SpeedSample>(maxPoints)
        for (bucket in 0 until maxPoints) {
            // Even split of [0, n) into maxPoints buckets; the last bucket
            // absorbs the remainder so every sample lands in exactly one bucket.
            val startIdx = (bucket.toLong() * n / maxPoints).toInt()
            val endIdx = ((bucket + 1).toLong() * n / maxPoints).toInt()
            if (endIdx <= startIdx) continue
            var tSum = 0L
            var sSum = 0.0
            for (j in startIdx until endIdx) {
                tSum += sorted[j].timestampMs
                sSum += sorted[j].speedKmh
            }
            val count = endIdx - startIdx
            out.add(SpeedSample(tSum / count, sSum / count))
        }
        return out
    }
}
