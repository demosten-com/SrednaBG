// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Testing
@testable import SrednaBGTracking

@Suite("SpeedInference")
struct SpeedInferenceTests {

    @Test
    func firstSampleReturnsReportedSpeed() {
        var si = SpeedInference()
        let s = si.combine(reportedKmh: 100, lat: 42, lng: 23, timestampMs: 1000)
        #expect(s == 100)
    }

    @Test
    func reportedSpeedWinsWhenLargerThanInferred() {
        var si = SpeedInference()
        _ = si.combine(reportedKmh: 100, lat: 42.0, lng: 23.0, timestampMs: 1000)
        // 5m east in 1s → ~18 km/h inferred; reported is 100 → reported wins.
        let s = si.combine(reportedKmh: 100, lat: 42.0, lng: 23.0001, timestampMs: 2000)
        #expect(s == 100)
    }

    @Test
    func inferredSpeedFillsForSilentReport() {
        var si = SpeedInference()
        _ = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.0, timestampMs: 1000)
        // ~111 m east of seed in 1s → ~400 km/h pre-clamp; SpeedInference caps at 250.
        let s = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.001, timestampMs: 2000)
        #expect(s > 0, "Inferred speed should fill in when report is 0")
        #expect(s <= 250, "Inferred speed must respect the 250 km/h ceiling")
    }

    @Test
    func skipsInferenceUnderMinimumDistance() {
        var si = SpeedInference()
        _ = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.0, timestampMs: 1000)
        // ~1m apart — below the 5m floor.
        let s = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.00001, timestampMs: 2000)
        #expect(s == 0)
    }

    @Test
    func resetClearsInferredSpeed() {
        var si = SpeedInference()
        _ = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.0, timestampMs: 1000)
        _ = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.001, timestampMs: 2000)
        si.reset()
        let s = si.combine(reportedKmh: 50, lat: 43.0, lng: 24.0, timestampMs: 10_000)
        #expect(s == 50, "Post-reset, first sample should be the reported value")
    }
}
