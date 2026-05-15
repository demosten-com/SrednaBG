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

    @Test
    func decaysOnStationaryAfterSpike() {
        // Reproduces the user-reported "Now shows 250 km/h while stationary"
        // bug. Without the decay branch, lastInferredKmh pins at 250 forever
        // because subsequent stationary samples (deltaM < 5m) never re-enter
        // the inference computation.
        var si = SpeedInference()
        _ = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.0, timestampMs: 1000)
        // ~111 m jump in 1 s → ~400 km/h pre-clamp → clamps at 250.
        let spike = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.001, timestampMs: 2000)
        #expect(spike > 200, "Spike sample should hit the clamp")
        // ~1 m drift, well under the 5 m floor.
        let stationary = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.00100001, timestampMs: 3000)
        #expect(stationary == 0, "Stationary sample after a spike must decay the inferred speed")
    }

    @Test
    func staleFixDoesNotUpdateState() {
        // A fix marked stale must not seed lastLat/Lng — otherwise a follow-
        // up fresh fix would diff against a cached position and synthesize
        // a phantom speed (the cold-start cause of the 250 bug).
        var si = SpeedInference()
        _ = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.0, timestampMs: 1000)
        // A stale fix arrives 100 m away — must NOT update lastLat/Lng.
        _ = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.001, timestampMs: 1500, freshFix: false)
        // Fresh fix ~1 m from the original seed — distance should be tiny
        // (deltaM ≈ 1 m), not the 100 m the stale interloper sat at.
        let s = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.00001, timestampMs: 2000)
        #expect(s == 0, "Fresh fix should diff against the original seed, not the stale interloper")
    }

    @Test
    func staleFixReturnsCurrentMaxWithoutMutating() {
        // After a spike pins lastInferredKmh at 250, a stale fix should
        // return max(reportedKmh, 250) but must not touch state — neither
        // decay nor re-seed the inference reference.
        var si = SpeedInference()
        _ = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.0, timestampMs: 1000)
        _ = si.combine(reportedKmh: 0, lat: 42.0, lng: 23.001, timestampMs: 2000)
        let pinnedBefore = si.lastInferredKmh
        let stale = si.combine(reportedKmh: 10, lat: 42.0, lng: 23.00100001, timestampMs: 3000, freshFix: false)
        #expect(stale == max(10, pinnedBefore))
        #expect(si.lastInferredKmh == pinnedBefore, "Stale fix must not decay state")
    }
}
