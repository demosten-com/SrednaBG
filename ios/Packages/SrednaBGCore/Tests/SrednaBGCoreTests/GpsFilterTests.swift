// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation
import Testing
@testable import SrednaBGCore

@Suite("GpsFilter")
struct GpsFilterTests {

    @Test
    func firstPointPassesThroughUnchanged() {
        var filter = GpsFilter()
        let point = GpsPoint(lat: 42.7, lng: 23.3, speed: 100.0, timestamp: epochBase, bearing: 90.0, accuracy: 5.0)
        let result = filter.filter(point)
        #expect(result.lat == point.lat)
        #expect(result.lng == point.lng)
        #expect(result.speed == point.speed)
    }

    @Test
    func sameTimestampFixBlendsInsteadOfResetting() {
        // A second fix sharing the previous timestamp (dt == 0 — FLP batching or a
        // QA feed with an overridden time_ms) must be a no-prediction measurement
        // blend, NOT a hard reset to the raw measurement. Converge first so the
        // position variance settles, then probe with an offset same-timestamp fix.
        var filter = GpsFilter()
        var converged = GpsPoint(lat: 42.700, lng: 23.300, speed: 100.0, timestamp: epochBase, bearing: 90.0, accuracy: 10.0)
        for i in 0..<15 {
            converged = filter.filter(
                GpsPoint(lat: 42.700, lng: 23.300, speed: 100.0, timestamp: epochBase + Int64(i) * 1000, bearing: 90.0, accuracy: 10.0)
            )
        }
        let lastTs = epochBase + 14 * 1000

        let raw = GpsPoint(lat: 42.710, lng: 23.310, speed: 200.0, timestamp: lastTs, bearing: 90.0, accuracy: 10.0)
        let result = filter.filter(raw)

        // Not a reset: pulled toward the new fix but anchored to the converged
        // estimate, so it differs from the raw measurement.
        #expect(abs(result.lat - raw.lat) > 1e-6, "dt==0 should blend, not reset to raw lat (\(result.lat) vs \(raw.lat))")
        #expect(
            abs(result.lat - converged.lat) < abs(result.lat - raw.lat),
            "blended lat should stay closer to the converged estimate than to raw"
        )
        // The speed channel is unit-consistent, so it's a clean partial step.
        #expect(result.speed < raw.speed, "dt==0 should blend speed, not reset to raw 200 km/h (was \(result.speed))")
    }

    @Test
    func stationaryNoisyReadingsConvergeToTruePosition() {
        let trueLat = 42.700
        let trueLng = 23.300
        var rng = SeededGaussianRNG(seed: 42)
        var filter = GpsFilter()

        var lastResult: GpsPoint?
        for i in 0..<30 {
            let noiseLat = rng.nextGaussian() * 10.0 / 111_320.0
            let noiseLng = rng.nextGaussian() * 10.0 / 111_320.0
            let point = GpsPoint(
                lat: trueLat + noiseLat,
                lng: trueLng + noiseLng,
                speed: 0.0,
                timestamp: epochBase + Int64(i) * 1000,
                bearing: 0.0,
                accuracy: 10.0
            )
            lastResult = filter.filter(point)
        }

        let result = lastResult!
        let errorLat = abs(result.lat - trueLat) * 111_320.0
        let errorLng = abs(result.lng - trueLng) * 111_320.0
        #expect(errorLat < 5.0, "Lat error should be < 5m, was \(errorLat)m")
        #expect(errorLng < 5.0, "Lng error should be < 5m, was \(errorLng)m")
    }

    @Test
    func filterTracksMovingVehicleWithinTolerance() {
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 120.0, intervalMs: 1000)
        let noisyTrace = addNoiseToTrace(trace, noiseMeters: 8.0)
        var filter = GpsFilter()

        var maxError = 0.0
        for i in noisyTrace.indices {
            let filtered = filter.filter(noisyTrace[i])
            let errorM = haversineDistance(filtered.lat, filtered.lng, trace[i].lat, trace[i].lng)
            if i > 5 { // skip initial convergence
                maxError = max(maxError, errorM)
            }
        }

        // On curved roads at speed, filter lags on direction changes — keep <200m.
        #expect(maxError < 200.0, "Max error should be < 200m, was \(maxError)m")
    }

    @Test
    func speedOutlierIsDampened() {
        var filter = GpsFilter()
        let points = [
            GpsPoint(lat: 42.700, lng: 23.300, speed: 120.0, timestamp: epochBase, bearing: 90.0, accuracy: 5.0),
            GpsPoint(lat: 42.701, lng: 23.301, speed: 120.0, timestamp: epochBase + 1000, bearing: 90.0, accuracy: 5.0),
            GpsPoint(lat: 42.702, lng: 23.302, speed: 120.0, timestamp: epochBase + 2000, bearing: 90.0, accuracy: 5.0),
            GpsPoint(lat: 42.703, lng: 23.303, speed: 300.0, timestamp: epochBase + 3000, bearing: 90.0, accuracy: 5.0), // spike
            GpsPoint(lat: 42.704, lng: 23.304, speed: 120.0, timestamp: epochBase + 4000, bearing: 90.0, accuracy: 5.0)
        ]

        var spikeFiltered = 0.0
        for point in points {
            let result = filter.filter(point)
            if point.timestamp == epochBase + 3000 {
                spikeFiltered = result.speed
            }
        }

        #expect(spikeFiltered < 250.0, "Spike should be dampened, was \(spikeFiltered)")
        #expect(spikeFiltered > 120.0, "Spike should still show increase, was \(spikeFiltered)")
    }

    @Test
    func resetClearsState() {
        var filter = GpsFilter()
        let point1 = GpsPoint(lat: 42.700, lng: 23.300, speed: 100.0, timestamp: epochBase, bearing: 90.0, accuracy: 5.0)
        _ = filter.filter(point1)

        filter.reset()

        let point2 = GpsPoint(lat: 43.000, lng: 24.000, speed: 80.0, timestamp: epochBase + 60_000, bearing: 180.0, accuracy: 5.0)
        let result = filter.filter(point2)
        #expect(result.lat == point2.lat)
        #expect(result.lng == point2.lng)
        #expect(result.speed == point2.speed)
    }

    @Test
    func largeTimeGapResetsFilterState() {
        var filter = GpsFilter()
        let point1 = GpsPoint(lat: 42.700, lng: 23.300, speed: 100.0, timestamp: epochBase, bearing: 90.0, accuracy: 5.0)
        _ = filter.filter(point1)

        // 60 second gap (> 30s threshold)
        let point2 = GpsPoint(lat: 42.800, lng: 23.400, speed: 120.0, timestamp: epochBase + 60_000, bearing: 90.0, accuracy: 5.0)
        let result = filter.filter(point2)

        #expect(result.lat == point2.lat)
        #expect(result.lng == point2.lng)
    }

    @Test
    func filteredSpeedIsNeverNegative() {
        var filter = GpsFilter()
        let point1 = GpsPoint(lat: 42.700, lng: 23.300, speed: 5.0, timestamp: epochBase, bearing: 90.0, accuracy: 10.0)
        _ = filter.filter(point1)

        let point2 = GpsPoint(lat: 42.700, lng: 23.300, speed: 0.0, timestamp: epochBase + 1000, bearing: 90.0, accuracy: 10.0)
        let result = filter.filter(point2)

        #expect(result.speed >= 0.0, "Filtered speed should never be negative")
    }
}
