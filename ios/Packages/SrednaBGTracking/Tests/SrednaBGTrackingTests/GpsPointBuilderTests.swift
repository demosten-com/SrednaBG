// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Testing
@testable import SrednaBGTracking

@Suite("GpsPointBuilder")
struct GpsPointBuilderTests {

    private func raw(
        lat: Double = 42.0,
        lng: Double = 23.0,
        speedMps: Double?,
        speedAccuracyMps: Double? = nil,
        timestampMs: Int64 = 1000,
        freshFix: Bool = true,
        course: Double? = 90
    ) -> RawLocationFix {
        RawLocationFix(
            lat: lat,
            lng: lng,
            course: course,
            speedMps: speedMps,
            timestampMs: timestampMs,
            accuracyM: 10,
            speedAccuracyMps: speedAccuracyMps,
            freshFix: freshFix
        )
    }

    @Test
    func suppressesReportedSpeedWhenWithinAccuracy() {
        // GPS Doppler noise floor: chip reports 0.5 m/s while sitting still,
        // accuracy is 0.8 m/s → "0" is within the 68% CI, so we suppress.
        var b = GpsPointBuilder()
        let (point, _) = b.build(raw(speedMps: 0.5, speedAccuracyMps: 0.8))
        #expect(point.speed == 0, "rawSpeed < speedAccuracy → reported is gated to 0")
    }

    @Test
    func passesReportedSpeedWhenAboveAccuracy() {
        // Real motion at 30 m/s (108 km/h) with 2 m/s accuracy → measurement
        // is well outside the noise floor, must flow through.
        var b = GpsPointBuilder()
        let (point, _) = b.build(raw(speedMps: 30, speedAccuracyMps: 2))
        #expect(point.speed > 100, "Real motion must pass the gate (got \(point.speed))")
    }

    @Test
    func treatsMissingAccuracyAsNoGate() {
        // If CoreLocation reports speed without speedAccuracy (older fixes,
        // simulator), don't synthesize a gate — trust the reported value.
        var b = GpsPointBuilder()
        let (point, _) = b.build(raw(speedMps: 5, speedAccuracyMps: nil))
        #expect(point.speed > 0, "Missing speedAccuracy must not suppress reported speed")
    }

    @Test
    func staleFixDoesNotSeedPositionReference() {
        // First sample is stale (cached "last known" from CoreLocation) at
        // an arbitrary spot; second sample is fresh ~1 m away from that
        // spot. Without the freshFix gate the second would diff against
        // the stale seed (deltaM ≈ 1 m, harmless) — but more importantly,
        // a THIRD fresh sample far from #2 must diff against #2, not be
        // tricked by the stale #1.
        var b = GpsPointBuilder()
        _ = b.build(raw(
            lat: 42.0, lng: 23.0,
            speedMps: 0, speedAccuracyMps: 0.5,
            timestampMs: 1000, freshFix: false
        ))
        // Stale fix should not have seeded position. Now a fresh fix
        // 200 m away from where the stale one claimed to be — if the
        // stale seeded, this would compute (200 m / 1 s) * 3.6 = 720
        // km/h → clamps at 250. With the fix, this is a "first fresh
        // sample" and returns 0.
        let (point, _) = b.build(raw(
            lat: 42.002, lng: 23.0,
            speedMps: 0, speedAccuracyMps: 0.5,
            timestampMs: 2000, freshFix: true
        ))
        #expect(point.speed < 50, "Stale first fix must not seed the inference reference (got \(point.speed))")
    }
}
