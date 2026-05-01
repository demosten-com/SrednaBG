// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Testing
@testable import SrednaBGTracking
import SrednaBGCore

@Suite("AdaptiveLocationCadence")
struct AdaptiveLocationCadenceTests {

    private static let trakiya = Zone(
        id: "trakiya-01-west",
        road: "АМ Тракия",
        roadLatin: "Trakiya",
        direction: "west",
        description: "Test",
        start: ZoneEndpoint(lat: 42.427, lng: 23.855),
        end: ZoneEndpoint(lat: 42.550, lng: 23.703),
        distanceM: 19160,
        speedLimits: SpeedLimits(car: 140, truck: 90, bus: 100),
        centerline: [[42.427, 23.855], [42.550, 23.703]],
        source: "test",
        lastVerified: "2026-04-12"
    )

    @Test
    func inZoneStateUsesOneSecondCadence() {
        let inZoneState = ZoneState.inZone(.init(
            zone: Self.trakiya,
            entryTime: 0,
            distanceTraveled: 0,
            avgSpeed: nil,
            speedStatus: SpeedStatus(avgSpeed: nil, maxSpeedForRemainder: 140, distanceRemaining: 0, timeRemaining: 0, isOverLimit: false),
            distanceRemaining: 0
        ))
        #expect(AdaptiveLocationCadence.intervalMs(for: inZoneState, position: nil, zones: [Self.trakiya]) == 1000)
    }

    @Test
    func exitingStateUsesOneSecondCadence() {
        let exiting = ZoneState.exiting(.init(zone: Self.trakiya, finalAvgSpeed: 130))
        #expect(AdaptiveLocationCadence.intervalMs(for: exiting, position: nil, zones: [Self.trakiya]) == 1000)
    }

    @Test
    func outsideWithNoPositionDefaultsToFar() {
        #expect(AdaptiveLocationCadence.intervalMs(for: .outside, position: nil, zones: [Self.trakiya]) == 5000)
    }

    @Test
    func outsideNearZoneStartUsesNearCadence() {
        // Within ~500m of zone start (well inside the 2km near threshold).
        let near = GpsPoint(lat: 42.430, lng: 23.855, speed: 100, timestamp: 0, bearing: 90)
        #expect(AdaptiveLocationCadence.intervalMs(for: .outside, position: near, zones: [Self.trakiya]) == 2000)
    }

    @Test
    func outsideFarFromAllZonesUsesFarCadence() {
        // ~hundreds of km away — definitely > 2km from any endpoint.
        let far = GpsPoint(lat: 44.0, lng: 26.0, speed: 100, timestamp: 0, bearing: 90)
        #expect(AdaptiveLocationCadence.intervalMs(for: .outside, position: far, zones: [Self.trakiya]) == 5000)
    }
}
