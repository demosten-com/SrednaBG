// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Testing
@testable import SrednaBGCore

@Suite("RoadMatcher")
struct RoadMatcherTests {

    @Test
    func isOnRoadTrueForPointOnCenterline() {
        let point = GpsPoint(
            lat: 42.480, lng: 23.800, speed: 130.0,
            timestamp: epochBase, bearing: 310.0
        )
        #expect(RoadMatcher.isOnRoad(point, TRAKIYA_T10))
    }

    @Test
    func isOnRoadTrueForPointWithin100m() {
        // ~50m north from a centerline point: at lat ~42.48, +0.00045 deg lat
        let point = GpsPoint(
            lat: 42.480 + 0.00045, lng: 23.800, speed: 130.0,
            timestamp: epochBase, bearing: 310.0
        )
        #expect(RoadMatcher.isOnRoad(point, TRAKIYA_T10))
    }

    @Test
    func isOnRoadFalseForDistantPoint() {
        let point = GpsPoint(
            lat: 43.0, lng: 25.0, speed: 130.0,
            timestamp: epochBase, bearing: 270.0
        )
        #expect(!RoadMatcher.isOnRoad(point, TRAKIYA_T10))
    }

    @Test
    func matchDirectionAcceptsCorrectDirection() throws {
        let polyBearing = try #require(polylineBearing(TRAKIYA_T10.centerline))
        #expect(RoadMatcher.matchDirection(polyBearing, TRAKIYA_T10))
    }

    @Test
    func matchDirectionRejectsOppositeDirection() throws {
        let polyBearing = try #require(polylineBearing(TRAKIYA_T10.centerline))
        let opposite = (polyBearing + 180).truncatingRemainder(dividingBy: 360)
        #expect(!RoadMatcher.matchDirection(opposite, TRAKIYA_T10))
    }

    @Test
    func matchDirectionAcceptsWithinTolerance() throws {
        let polyBearing = try #require(polylineBearing(TRAKIYA_T10.centerline))
        // 40 degrees off should still be within 45 tolerance
        #expect(RoadMatcher.matchDirection(polyBearing + 40, TRAKIYA_T10))
    }

    @Test
    func findMatchingZoneReturnsCorrectZone() throws {
        let allZones = [TRAKIYA_T10, HEMUS_H12, I4_10]
        let bearing = try #require(polylineBearing(TRAKIYA_T10.centerline))
        let point = GpsPoint(
            lat: 42.480, lng: 23.800, speed: 130.0,
            timestamp: epochBase, bearing: bearing
        )
        let matched = try #require(RoadMatcher.findMatchingZone(point, allZones))
        #expect(matched.id == "trakiya-01-west")
    }

    @Test
    func findMatchingZoneReturnsNilWhenNoMatch() {
        let allZones = [TRAKIYA_T10, HEMUS_H12, I4_10]
        let point = GpsPoint(
            lat: 44.0, lng: 26.0, speed: 100.0,
            timestamp: epochBase, bearing: 90.0
        )
        #expect(RoadMatcher.findMatchingZone(point, allZones) == nil)
    }

    @Test
    func findMatchingZoneRejectsWrongDirection() throws {
        let allZones = [TRAKIYA_T10] // only westbound
        let bearing = try #require(polylineBearing(TRAKIYA_T10.centerline))
        let oppositeBearing = (bearing + 180).truncatingRemainder(dividingBy: 360)
        let point = GpsPoint(
            lat: 42.480, lng: 23.800, speed: 130.0,
            timestamp: epochBase, bearing: oppositeBearing
        )
        #expect(RoadMatcher.findMatchingZone(point, allZones) == nil)
    }

    @Test
    func distanceToZoneStart() {
        let point = GpsPoint(
            lat: 42.427, lng: 23.855, speed: 130.0,
            timestamp: epochBase, bearing: 310.0
        )
        #expect(RoadMatcher.distanceToZoneStart(point, TRAKIYA_T10) < 10)
    }

    @Test
    func distanceToZoneEnd() {
        let point = GpsPoint(
            lat: 42.550, lng: 23.703, speed: 130.0,
            timestamp: epochBase, bearing: 310.0
        )
        #expect(RoadMatcher.distanceToZoneEnd(point, TRAKIYA_T10) < 10)
    }
}
