// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation
import Testing
@testable import SrednaBGCore

// Each engine behavior gets its own focused @Test; the suite naturally runs long.
// swiftlint:disable type_body_length
@Suite("ZoneDetector")
struct ZoneDetectorTests {

    @Test
    func fullTraversalAtLegalSpeed() throws {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0)
        #expect(trace.count > 10, "Trace should have many points")

        var sawOutside = false
        var sawInZone = false
        var sawExiting = false

        for point in trace {
            let state = detector.update(point)
            switch state {
            case .outside:
                sawOutside = true
            case .inZone(let inZone):
                sawInZone = true
                #expect(!inZone.speedStatus.isOverLimit, "Should not be over limit at 130 km/h")
            case .exiting(let exiting):
                sawExiting = true
                let avg = try #require(exiting.finalAvgSpeed)
                #expect(avg > 100, "Final speed \(avg) too low")
                #expect(avg < 180, "Final speed \(avg) too high")
            }
        }

        #expect(sawOutside, "Should have been Outside initially")
        #expect(sawInZone, "Should have been InZone during traversal")
        #expect(sawExiting, "Should have Exiting state")
    }

    @Test
    func fullTraversalWhileSpeeding() throws {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 160.0)

        var lastInZone: ZoneState.InZone?
        for point in trace {
            let state = detector.update(point)
            if case .inZone(let inZone) = state { lastInZone = inZone }
        }

        let last = try #require(lastInZone, "Should have been in zone")
        #expect(last.speedStatus.isOverLimit, "Should be over limit at 160 km/h")
    }

    @Test
    func stopDetectionExcludesLongStop() throws {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateTraceWithStop(
            zone: TRAKIYA_T10,
            speedKmh: 130.0,
            stopDurationMs: 120_000 // 2-minute stop
        )

        var exitState: ZoneState.Exiting?
        for point in trace {
            let state = detector.update(point)
            if case .exiting(let e) = state { exitState = e }
        }

        let exit = try #require(exitState, "Should have exited zone")
        let avg = try #require(exit.finalAvgSpeed)
        // With stop excluded, avg should reflect driving speed (~130), not the diluted average.
        #expect(avg > 80, "Avg speed \(avg) too low (stop not excluded?)")
    }

    @Test
    func briefStopUnder30sIsNotExcluded() throws {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateTraceWithStop(
            zone: TRAKIYA_T10,
            speedKmh: 130.0,
            stopDurationMs: 20_000 // 20-second stop, under threshold
        )

        var exitState: ZoneState.Exiting?
        for point in trace {
            let state = detector.update(point)
            if case .exiting(let e) = state { exitState = e }
        }

        let exit = try #require(exitState, "Should have exited zone")
        let avg = try #require(exit.finalAvgSpeed)
        #expect(avg < 130, "Brief stop should count against driver, but avg=\(avg)")
    }

    @Test
    func gpsDropoutDoesNotAddPhantomDistance() {
        let traceNormal = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0)
        let traceDropout = generateTraceWithDropout(
            zone: TRAKIYA_T10,
            speedKmh: 130.0,
            dropoutDurationMs: 15_000
        )

        var detectorNormal = ZoneDetector(zones: [TRAKIYA_T10])
        var detectorDropout = ZoneDetector(zones: [TRAKIYA_T10])

        var normalMaxDist = 0.0
        var dropoutMaxDist = 0.0

        for point in traceNormal {
            let state = detectorNormal.update(point)
            if case .inZone(let inZone) = state {
                normalMaxDist = max(normalMaxDist, inZone.distanceTraveled)
            }
        }

        for point in traceDropout {
            let state = detectorDropout.update(point)
            if case .inZone(let inZone) = state {
                dropoutMaxDist = max(dropoutMaxDist, inZone.distanceTraveled)
            }
        }

        #expect(dropoutMaxDist < normalMaxDist,
                "Dropout should have less distance: \(dropoutMaxDist) vs \(normalMaxDist)")
    }

    @Test
    func coldStartMidZoneEntersWithReducedEffectiveDistance() throws {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let midBearing = try #require(polylineBearing(TRAKIYA_T10.centerline))
        let midPoint = GpsPoint(
            lat: 42.510, lng: 23.770, speed: 130.0,
            timestamp: epochBase, bearing: midBearing
        )

        let state = detector.update(midPoint)
        guard case .inZone(let inZone) = state else {
            Issue.record("Should enter zone from mid-point cold-start, got \(state)")
            return
        }
        #expect(inZone.distanceRemaining < Double(TRAKIYA_T10.distanceM),
                "Effective remaining distance \(inZone.distanceRemaining) should be less than full zone \(TRAKIYA_T10.distanceM)")
        #expect(inZone.distanceRemaining > 1000,
                "Mid-zone cold-start should still have meaningful distance remaining (\(inZone.distanceRemaining))")
    }

    @Test
    func coldStartVeryNearZoneEndStaysOutside() throws {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let bearing = try #require(polylineBearing(TRAKIYA_T10.centerline))
        let nearEnd = GpsPoint(
            lat: TRAKIYA_T10.end.lat,
            lng: TRAKIYA_T10.end.lng,
            speed: 130.0,
            timestamp: epochBase,
            bearing: bearing
        )

        let state = detector.update(nearEnd)
        #expect(state == .outside, "Should not enter zone when already at the exit endpoint")
    }

    @Test
    func distanceRemainingTracksGpsPositionAlongPolyline() {
        // Regression: iOS used to surface `AverageSpeedCalc`'s
        // `zoneDistance - distanceTraveled` (the time-integrated traveled
        // distance) instead of Android's polyline-arc-length from the live
        // GPS position. With a wide-margin zone the two diverge — the time-
        // integrated value undershoots the polyline arc-length because the
        // centerline winds while the integrator just sums |speed|·dt. The
        // /screenshot-app harness surfaced "0.2 km Остават" in mid-zone
        // shots that should have shown several kilometres.
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0)

        var firstInZoneRemaining: Double?
        var midInZoneRemaining: Double?
        var seenInZone = 0
        for point in trace {
            let state = detector.update(point)
            if case .inZone(let inZone) = state {
                seenInZone += 1
                if firstInZoneRemaining == nil { firstInZoneRemaining = inZone.distanceRemaining }
                // ~halfway through the in-zone span — far enough that the
                // polyline arc-length has measurably decreased but well
                // before the EXIT_DISTANCE_M (300m) tripwire fires.
                if seenInZone == 20 { midInZoneRemaining = inZone.distanceRemaining }
            }
        }

        let first = firstInZoneRemaining ?? -1
        let mid = midInZoneRemaining ?? -1
        #expect(first > 0, "InZone state should publish a positive distanceRemaining")
        #expect(mid > 0, "Mid-trace distanceRemaining should still be positive (\(mid))")
        #expect(mid < first,
                "distanceRemaining should shrink as the GPS advances along the polyline (first=\(first), mid=\(mid))")
        // The mid-trace value must still be meaningful — the bug we're catching
        // collapsed it toward 0 when the centerline winds away from the chord.
        #expect(mid > 1000,
                "distanceRemaining at trace midpoint should be > 1km for TRAKIYA_T10, got \(mid)")
    }

    @Test
    func exitOnLeavingRoad() {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0)

        var enteredZone = false
        for point in trace.prefix(10) {
            let state = detector.update(point)
            if case .inZone = state {
                enteredZone = true
                break
            }
        }
        #expect(enteredZone, "Should have entered zone")

        let offRoadPoint = GpsPoint(
            lat: 42.6, lng: 23.9, speed: 80.0,
            timestamp: epochBase + 20_000,
            bearing: 180.0
        )
        let state = detector.update(offRoadPoint)
        if case .exiting = state {} else {
            Issue.record("Should exit when leaving road, got \(state)")
        }
    }

    @Test
    func resetClearsState() {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0)

        for point in trace.prefix(10) {
            _ = detector.update(point)
        }

        detector.reset()
        #expect(detector.state == .outside, "Reset should return to Outside")
    }

    @Test
    func exitingTransitionsToOutsideOnNextUpdate() {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0)

        var exitingIdx = -1
        for (idx, point) in trace.enumerated() {
            let state = detector.update(point)
            if case .exiting = state {
                exitingIdx = idx
                break
            }
        }
        #expect(exitingIdx > 0, "Should have reached Exiting state")

        if exitingIdx + 1 < trace.count {
            let state = detector.update(trace[exitingIdx + 1])
            switch state {
            case .outside, .inZone: break
            case .exiting:
                Issue.record("After Exiting, should be Outside or in new zone, got \(state)")
            }
        }
    }

    @Test
    func oppositeDirectionDoesNotMatchZone() {
        var detectorOpposite = ZoneDetector(zones: [TRAKIYA_T10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10_OPPOSITE, speedKmh: 130.0)

        var sawInZone = false
        for point in trace {
            let state = detectorOpposite.update(point)
            if case .inZone = state { sawInZone = true }
        }

        #expect(!sawInZone, "Opposite direction should not enter zone")
    }

    @Test
    func reentryAlwaysStartsFresh() {
        let trace = generateReentryTrace(
            zone: TRAKIYA_T10,
            speedKmh: 130.0,
            exitAtFraction: 0.3,
            offRoadDurationMs: 120_000
        )

        var det = ZoneDetector(zones: [TRAKIYA_T10])
        var entrySnapshots: [ZoneState.InZone] = []
        var prevEntryTime: Int64?

        for point in trace {
            let state = det.update(point)
            switch state {
            case .inZone(let inZone):
                if prevEntryTime == nil || inZone.entryTime != prevEntryTime {
                    entrySnapshots.append(inZone)
                    prevEntryTime = inZone.entryTime
                }
            default:
                prevEntryTime = nil
            }
        }

        #expect(entrySnapshots.count >= 2,
                "Should have entered zone twice (initial + re-entry), got \(entrySnapshots.count)")
        let first = entrySnapshots.first!
        let reentry = entrySnapshots.last!
        #expect(reentry.entryTime > first.entryTime,
                "Re-entry time \(reentry.entryTime) should be after initial \(first.entryTime)")
        #expect(reentry.distanceTraveled < 5.0,
                "Re-entry should start with ~0 distanceTraveled, got \(reentry.distanceTraveled)")
    }

    @Test
    func reentryAfterTimestampRewindStartsFresh() throws {
        var det = ZoneDetector(zones: [TRAKIYA_T10])

        // Phase 1: drive partway through the zone.
        let trace1 = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0, startTime: epochBase)
        var firstEntryTime: Int64?
        var firstMaxDistance = 0.0
        for point in trace1.prefix(20) {
            let state = det.update(point)
            if case .inZone(let inZone) = state {
                if firstEntryTime == nil { firstEntryTime = inZone.entryTime }
                firstMaxDistance = max(firstMaxDistance, inZone.distanceTraveled)
            }
        }
        let firstEntry = try #require(firstEntryTime, "Should have entered zone in phase 1")
        #expect(firstMaxDistance > 100,
                "Should have accumulated some distance in phase 1 (got \(firstMaxDistance))")

        // Phase 2: force exit via an off-road point.
        let offRoadTime = trace1[19].timestamp + 1000
        _ = det.update(GpsPoint(lat: 42.6, lng: 23.9, speed: 80.0, timestamp: offRoadTime, bearing: 180.0))

        // Phase 3: replay the GPX with timestamps earlier than the exit time.
        let trace2 = generateGpsTrace(
            zone: TRAKIYA_T10,
            speedKmh: 130.0,
            startTime: firstEntry - 60_000
        )
        var rewoundEntryTime: Int64?
        var rewoundInitialDistance: Double?
        for point in trace2.prefix(20) {
            let state = det.update(point)
            if case .inZone(let inZone) = state, rewoundEntryTime == nil {
                rewoundEntryTime = inZone.entryTime
                rewoundInitialDistance = inZone.distanceTraveled
            }
        }

        let rewoundEntry = try #require(rewoundEntryTime, "Should have re-entered zone after rewind")
        let rewoundDist = try #require(rewoundInitialDistance)
        #expect(rewoundEntry < firstEntry,
                "Rewound entry time \(rewoundEntry) should be before original \(firstEntry)")
        #expect(rewoundDist < 5.0,
                "Re-entry after rewind should start with ~0 distance, got \(rewoundDist)")
    }

    @Test
    func noisyGpsTraceStillDetectsZone() {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0)
        let noisyTrace = addNoiseToTrace(trace, noiseMeters: 15.0)

        var sawInZone = false
        var sawExiting = false
        for point in noisyTrace {
            let state = detector.update(point)
            if case .inZone = state { sawInZone = true }
            if case .exiting = state { sawExiting = true }
        }

        #expect(sawInZone, "Noisy trace should still detect zone entry")
        #expect(sawExiting, "Noisy trace should still detect zone exit")
    }

    @Test
    func veryHighSpeedTraversalWorksCorrectly() throws {
        var detector = ZoneDetector(zones: [TRAKIYA_T10, HEMUS_H12, I4_10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 220.0)

        var sawInZone = false
        var sawExiting = false
        var lastExitState: ZoneState.Exiting?

        for point in trace {
            let state = detector.update(point)
            if case .inZone = state { sawInZone = true }
            if case .exiting(let e) = state {
                sawExiting = true
                lastExitState = e
            }
        }

        #expect(sawInZone, "Should enter zone at high speed")
        #expect(sawExiting, "Should exit zone at high speed")
        let exit = try #require(lastExitState)
        let avg = try #require(exit.finalAvgSpeed)
        #expect(avg > 150, "High speed should register")
        #expect(avg > 140, "220 km/h should be over 140 limit")
    }

    @Test
    func motorwayZoneMatchesAtWiderDistance() throws {
        // Trakiya is a motorway (road starts with "АМ ")
        // Point 120m from centerline — match motorway (150m) but not national road (100m)
        let midBearing = try #require(polylineBearing(TRAKIYA_T10.centerline))
        let offsetLat = 120.0 / 111_320.0
        let nearPoint = GpsPoint(
            lat: TRAKIYA_T10.start.lat + offsetLat,
            lng: TRAKIYA_T10.start.lng,
            speed: 130.0,
            timestamp: epochBase,
            bearing: midBearing
        )

        #expect(RoadMatcher.isOnRoad(nearPoint, TRAKIYA_T10),
                "120m from motorway centerline should be on road (150m threshold)")

        let nearNationalPoint = GpsPoint(
            lat: NATIONAL_ROAD_ZONE.centerline[0][0] + offsetLat,
            lng: NATIONAL_ROAD_ZONE.centerline[0][1],
            speed: 80.0,
            timestamp: epochBase,
            bearing: 90.0
        )
        #expect(!RoadMatcher.isOnRoad(nearNationalPoint, NATIONAL_ROAD_ZONE),
                "120m from national road centerline should NOT be on road (100m threshold)")
    }

    // iOS-only: vehicle-type-aware ZoneDetector. Truck on a 140 km/h motorway is
    // limited to 90 km/h, so 120 km/h must register as over-limit.
    @Test
    func vehicleTypeChangesEffectiveLimit() throws {
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 120.0)
        var carDetector = ZoneDetector(zones: [TRAKIYA_T10])
        var truckDetector = ZoneDetector(zones: [TRAKIYA_T10])

        var carLast: ZoneState.InZone?
        var truckLast: ZoneState.InZone?
        for point in trace {
            if case .inZone(let s) = carDetector.update(point, vehicleType: .car) { carLast = s }
            if case .inZone(let s) = truckDetector.update(point, vehicleType: .truck) { truckLast = s }
        }

        let car = try #require(carLast)
        let truck = try #require(truckLast)
        #expect(!car.speedStatus.isOverLimit, "Car at 120 in 140 zone is fine")
        #expect(truck.speedStatus.isOverLimit, "Truck at 120 in 90 (truck) zone is over limit")
    }

    @Test
    func reversedCenterlineStillEntersCorrectZone() throws {
        // Regression for the end-first centerline server bug: the same zone with
        // its centerline reversed (start/end/id unchanged) must still enter the
        // correct sibling when driven forward. Without endpoint orientation the
        // reversed centerline's first→last bearing points the opposite way, so the
        // forward trace's direction never matches and the zone is never entered.
        let reversed = TRAKIYA_T10.with(centerline: Array(TRAKIYA_T10.centerline.reversed()))
        var detector = ZoneDetector(zones: [reversed])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0)

        var firstInZoneId: String?
        var inZoneIds: [String] = []
        for point in trace {
            if case .inZone(let inZone) = detector.update(point) {
                if firstInZoneId == nil { firstInZoneId = inZone.zone.id }
                inZoneIds.append(inZone.zone.id)
            }
        }

        #expect(!inZoneIds.isEmpty, "Should have entered the zone despite the reversed centerline")
        #expect(firstInZoneId == "trakiya-01-west",
                "Forward drive should enter trakiya-01-west, got \(firstInZoneId ?? "nil")")
    }

    @Test
    func transientOffRoadBlipStaysButSustainedExits() throws {
        // A single off-road fix (Kalman lag on a bend / momentary glitch) must be
        // absorbed; only a sustained departure exits. Mirrors the Android
        // hysteresis regression.
        var detector = ZoneDetector(zones: [TRAKIYA_T10])
        let trace = generateGpsTrace(zone: TRAKIYA_T10, speedKmh: 130.0)

        var base: GpsPoint?
        for point in trace {
            if case .inZone = detector.update(point) {
                base = point
                break
            }
        }
        let inZonePoint = try #require(base, "Should have entered the zone")

        // ~330 m perpendicular off the centerline — past the 150 m motorway band
        // but well within offRoadHardM, i.e. a blip, not a departure.
        func offRoad(_ seq: Int64) -> GpsPoint {
            GpsPoint(
                lat: inZonePoint.lat + 0.003,
                lng: inZonePoint.lng,
                speed: 130.0,
                timestamp: inZonePoint.timestamp + seq * 1000,
                bearing: inZonePoint.bearing
            )
        }

        if case .inZone = detector.update(offRoad(1)) {} else {
            Issue.record("1st off-road fix must be absorbed")
        }
        if case .inZone = detector.update(offRoad(2)) {} else {
            Issue.record("2nd off-road fix must be absorbed")
        }
        if case .exiting = detector.update(offRoad(3)) {} else {
            Issue.record("Sustained off-road (>= offRoadExitGraceFixes) must exit")
        }
    }
}
// swiftlint:enable type_body_length
