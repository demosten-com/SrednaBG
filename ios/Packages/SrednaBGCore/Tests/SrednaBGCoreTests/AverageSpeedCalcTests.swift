// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation
import Testing
@testable import SrednaBGCore

@Suite("AverageSpeedCalc")
struct AverageSpeedCalcTests {

    @Test
    func normalDrivingUnderLimit() throws {
        // 10 km in 300 seconds, zone 19160m, limit 140 km/h
        let status = AverageSpeedCalc.calculate(
            entryTime: 0,
            currentTime: 300_000,
            stopDurationMs: 0,
            distanceTraveled: 10_000,
            zoneDistance: 19_160,
            speedLimitKmh: 140
        )

        let avg = try #require(status.avgSpeed)
        #expect(approxEqual(avg, 120.0, tol: 0.5))
        #expect(!status.isOverLimit)
        #expect(approxEqual(status.distanceRemaining, 9160.0, tol: 1.0))
        #expect(status.timeRemaining > 0)
        #expect(status.maxSpeedForRemainder > 140)
    }

    @Test
    func speedingScenario() throws {
        // 10 km in 240 seconds = 150 km/h average
        let status = AverageSpeedCalc.calculate(
            entryTime: 0,
            currentTime: 240_000,
            stopDurationMs: 0,
            distanceTraveled: 10_000,
            zoneDistance: 19_160,
            speedLimitKmh: 140
        )

        let avg = try #require(status.avgSpeed)
        #expect(approxEqual(avg, 150.0, tol: 0.5))
        #expect(status.isOverLimit)
        #expect(status.maxSpeedForRemainder < 140)
    }

    @Test
    func drivingWithStopDeduction() throws {
        // 10 km in 400 seconds total, 100 seconds stopped → active 300s ≈ 120 km/h
        let status = AverageSpeedCalc.calculate(
            entryTime: 0,
            currentTime: 400_000,
            stopDurationMs: 100_000,
            distanceTraveled: 10_000,
            zoneDistance: 19_160,
            speedLimitKmh: 140
        )

        let avg = try #require(status.avgSpeed)
        #expect(approxEqual(avg, 120.0, tol: 0.5))
        #expect(!status.isOverLimit)
    }

    @Test
    func timeFullySpent() {
        // 15 km in 500 seconds at limit 140 km/h
        // Required time = 19160 / (140/3.6) ≈ 492.7s; remaining negative → clamped to MAX (250)
        let status = AverageSpeedCalc.calculate(
            entryTime: 0,
            currentTime: 500_000,
            stopDurationMs: 0,
            distanceTraveled: 15_000,
            zoneDistance: 19_160,
            speedLimitKmh: 140
        )

        #expect(status.timeRemaining < 0)
        #expect(status.maxSpeedForRemainder == 250.0)
        #expect(status.distanceRemaining > 0)
    }

    @Test
    func nearZoneEndClampsRemainderTo250() {
        // Near the end of a short remaining slice, raw quotient would be > 6000 km/h.
        // 18 km traveled of 19.16 km zone in 492 seconds (limit 140 km/h →
        // required ≈ 492.7s) leaves ~0.7s of legal time for ~1160 m of road.
        let status = AverageSpeedCalc.calculate(
            entryTime: 0,
            currentTime: 492_000,
            stopDurationMs: 0,
            distanceTraveled: 18_000,
            zoneDistance: 19_160,
            speedLimitKmh: 140
        )

        #expect(status.timeRemaining > 0)
        #expect(status.distanceRemaining > 0)
        #expect(status.maxSpeedForRemainder == 250.0)
    }

    @Test
    func zeroElapsedTimeEdgeCase() {
        let status = AverageSpeedCalc.calculate(
            entryTime: 1000,
            currentTime: 1000,
            stopDurationMs: 0,
            distanceTraveled: 0,
            zoneDistance: 19_160,
            speedLimitKmh: 140
        )

        #expect(status.avgSpeed == nil)
        #expect(!status.isOverLimit)
        #expect(approxEqual(status.distanceRemaining, 19_160.0, tol: 1.0))
    }

    @Test
    func avgSpeedNullJustBelowThresholdAndNonNullAtThreshold() throws {
        let warming = AverageSpeedCalc.calculate(
            entryTime: 0,
            currentTime: 999,
            stopDurationMs: 0,
            distanceTraveled: 35,
            zoneDistance: 19_160,
            speedLimitKmh: 140
        )
        #expect(warming.avgSpeed == nil)

        let firstSample = AverageSpeedCalc.calculate(
            entryTime: 0,
            currentTime: 1_000,
            stopDurationMs: 0,
            distanceTraveled: 36, // ~130 km/h for 1s
            zoneDistance: 19_160,
            speedLimitKmh: 140
        )
        let avg = try #require(firstSample.avgSpeed)
        #expect(approxEqual(avg, 129.6, tol: 0.1))
    }

    @Test
    func distanceAlreadyExceeded() {
        let status = AverageSpeedCalc.calculate(
            entryTime: 0,
            currentTime: 500_000,
            stopDurationMs: 0,
            distanceTraveled: 20_000,
            zoneDistance: 19_160,
            speedLimitKmh: 140
        )

        #expect(approxEqual(status.distanceRemaining, 0.0, tol: 0.01))
        #expect(approxEqual(status.maxSpeedForRemainder, 0.0, tol: 0.01))
    }

    @Test
    func nationalRoadLowerSpeedLimit() throws {
        // I-4 zone with 90 km/h limit; 5000/200 * 3.6 = 90 km/h exactly → not strictly over
        let status = AverageSpeedCalc.calculate(
            entryTime: 0,
            currentTime: 200_000,
            stopDurationMs: 0,
            distanceTraveled: 5_000,
            zoneDistance: 9_200,
            speedLimitKmh: 90
        )

        let avg = try #require(status.avgSpeed)
        #expect(approxEqual(avg, 90.0, tol: 0.5))
        #expect(!status.isOverLimit)
    }
}
