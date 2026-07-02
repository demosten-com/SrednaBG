// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

// A single speed-over-time reading captured during a zone traversal. The app
// layer appends one per accepted GPS fix while `ZoneState.inZone`; the finalized
// series is stored with the history record and drawn on the detail graph.
//
// Mirrors the Kotlin `SpeedSample` in `android/core/.../HistoryStats.kt` — keep the
// two in sync (same fields, same `sustainedExtremes` / `runningAverage` /
// `downsample` semantics, same shared JSON fixtures under `Tests/.../Resources/`).
//
// - `timestampMs`: fix time as epoch **milliseconds**.
// - `speedKmh`: ground speed in **km/h**.
public struct SpeedSample: Sendable, Codable, Equatable {
    public let timestampMs: Int64
    public let speedKmh: Double

    public init(timestampMs: Int64, speedKmh: Double) {
        self.timestampMs = timestampMs
        self.speedKmh = speedKmh
    }
}

/// Pure statistics over a captured `SpeedSample` series. No platform or engine
/// dependencies so it unit-tests on any host and hand-ports 1:1 from the Kotlin
/// `HistoryStats` object.
public enum HistoryStats {

    /// Default smoothing window for `sustainedExtremes`, in milliseconds.
    public static let defaultWindowMs: Int64 = 3000

    /// Default cap for `downsample`.
    public static let defaultMaxPoints: Int = 500

    /// Sustained min/max speed over the series.
    ///
    /// A raw min/max would report a single-sample GPS spike or drop as the
    /// extreme — "top speed 231" from one bad fix. Instead we first smooth the
    /// series with a centered moving-average window (`windowMs`, default 3 s):
    /// each point becomes the mean of the samples within ±`windowMs`/2 of it, so
    /// a lone outlier is diluted by its neighbours and can't dominate. The
    /// extremes of the *smoothed* series are what a driver actually sustained for
    /// a few seconds.
    ///
    /// - Returns: `(min, max)` in km/h. `(0, 0)` for an empty series; `(speed,
    ///   speed)` for a single sample.
    public static func sustainedExtremes(
        _ samples: [SpeedSample],
        windowMs: Int64 = defaultWindowMs
    ) -> (min: Double, max: Double) {
        if samples.isEmpty { return (0.0, 0.0) }
        if samples.count == 1 { return (samples[0].speedKmh, samples[0].speedKmh) }

        let sorted = samples.sorted { $0.timestampMs < $1.timestampMs }
        let half = windowMs / 2
        var minValue = Double.greatestFiniteMagnitude
        var maxValue = -Double.greatestFiniteMagnitude
        // Two-pointer sliding window over the time-sorted series: [lo, hi) is the
        // set of samples within ±half of sorted[i]. Both pointers advance
        // monotonically, so this is O(n) rather than O(n·window).
        var lo = 0
        var hi = 0
        for i in sorted.indices {
            let t = sorted[i].timestampMs
            while lo < sorted.count && sorted[lo].timestampMs < t - half { lo += 1 }
            if hi < lo { hi = lo }
            while hi < sorted.count && sorted[hi].timestampMs <= t + half { hi += 1 }
            var sum = 0.0
            for j in lo..<hi { sum += sorted[j].speedKmh }
            let smoothed = sum / Double(hi - lo)
            if smoothed < minValue { minValue = smoothed }
            if smoothed > maxValue { maxValue = smoothed }
        }
        return (minValue, maxValue)
    }

    /// The **running** (cumulative) average speed at each sample — the metric this
    /// app is actually about. Point `i` is the time-weighted mean speed over
    /// `[t0, t_i]` (trapezoidal integral of speed over elapsed time), so the series
    /// starts at the first sample's speed and converges toward the final trip
    /// average. Plotted as the graph's average line, it evolves with the drive
    /// instead of being a flat final-average reference.
    ///
    /// - Returns: one `SpeedSample` per input (same timestamps), `speedKmh` holding
    ///   the running average up to and including that point. Empty in, empty out.
    public static func runningAverage(_ samples: [SpeedSample]) -> [SpeedSample] {
        if samples.isEmpty { return [] }
        let sorted = samples.sorted { $0.timestampMs < $1.timestampMs }
        let t0 = sorted[0].timestampMs
        var out = [SpeedSample]()
        out.reserveCapacity(sorted.count)
        out.append(SpeedSample(timestampMs: sorted[0].timestampMs, speedKmh: sorted[0].speedKmh))
        var integral = 0.0 // km/h · ms
        for i in 1..<sorted.count {
            let dt = Double(sorted[i].timestampMs - sorted[i - 1].timestampMs)
            integral += (sorted[i - 1].speedKmh + sorted[i].speedKmh) / 2.0 * dt
            let elapsed = Double(sorted[i].timestampMs - t0)
            let avg = elapsed > 0.0 ? integral / elapsed : sorted[i].speedKmh
            out.append(SpeedSample(timestampMs: sorted[i].timestampMs, speedKmh: avg))
        }
        return out
    }

    /// Downsample to at most `maxPoints` samples for storage / plotting.
    ///
    /// Pass-through when the series already fits (a short zone at 1 Hz stays
    /// intact). Otherwise the series is split into `maxPoints` contiguous buckets
    /// and each collapses to one sample whose timestamp and speed are the bucket
    /// mean — preserving the overall shape without unbounded storage (the longest
    /// zones at 1 Hz run well past 500 samples).
    public static func downsample(
        _ samples: [SpeedSample],
        maxPoints: Int = defaultMaxPoints
    ) -> [SpeedSample] {
        precondition(maxPoints > 0, "maxPoints must be positive")
        if samples.count <= maxPoints { return samples }
        let sorted = samples.sorted { $0.timestampMs < $1.timestampMs }
        let n = sorted.count
        var out = [SpeedSample]()
        out.reserveCapacity(maxPoints)
        for bucket in 0..<maxPoints {
            // Even split of [0, n) into maxPoints buckets; the last bucket
            // absorbs the remainder so every sample lands in exactly one bucket.
            let startIdx = Int(Int64(bucket) * Int64(n) / Int64(maxPoints))
            let endIdx = Int(Int64(bucket + 1) * Int64(n) / Int64(maxPoints))
            if endIdx <= startIdx { continue }
            var tSum: Int64 = 0
            var sSum = 0.0
            for j in startIdx..<endIdx {
                tSum += sorted[j].timestampMs
                sSum += sorted[j].speedKmh
            }
            let count = Int64(endIdx - startIdx)
            out.append(SpeedSample(timestampMs: tSum / count, speedKmh: sSum / Double(count)))
        }
        return out
    }
}
