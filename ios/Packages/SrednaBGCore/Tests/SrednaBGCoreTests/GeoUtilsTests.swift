// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation
import Testing
@testable import SrednaBGCore

@Suite("GeoUtils")
struct GeoUtilsTests {

    @Test
    func haversineSamePointIsZero() {
        #expect(approxEqual(haversineDistance(42.5, 23.8, 42.5, 23.8), 0.0, tol: 0.01))
    }

    @Test
    func haversineSofiaToPlovdiv() {
        // Sofia (42.6977, 23.3219) to Plovdiv (42.1354, 24.7453) ~ 130 km
        let dist = haversineDistance(42.6977, 23.3219, 42.1354, 24.7453)
        #expect(approxEqual(dist, 130_000.0, tol: 5_000.0))
    }

    @Test
    func haversineSofiaToBurgas() {
        // Sofia to Burgas ~ 340 km (straight line)
        let dist = haversineDistance(42.6977, 23.3219, 42.5048, 27.4626)
        #expect(approxEqual(dist, 340_000.0, tol: 20_000.0))
    }

    @Test
    func haversineOneDegreeLatitudeAtEquator() {
        let dist = haversineDistance(0.0, 0.0, 1.0, 0.0)
        #expect(approxEqual(dist, 111_195.0, tol: 200.0))
    }

    @Test
    func pointToSegmentDistanceOnSegment() {
        let dist = pointToSegmentDistance(
            pLat: 42.450, pLng: 23.830,
            aLat: 42.427, aLng: 23.855,
            bLat: 42.550, bLng: 23.703
        )
        #expect(dist < 500)
    }

    @Test
    func pointToSegmentDistanceAtVertex() {
        let dist = pointToSegmentDistance(
            pLat: 42.427, pLng: 23.855,
            aLat: 42.427, aLng: 23.855,
            bLat: 42.550, bLng: 23.703
        )
        #expect(approxEqual(dist, 0.0, tol: 1.0))
    }

    @Test
    func pointToSegmentDistanceFarAway() {
        let dist = pointToSegmentDistance(
            pLat: 43.0, pLng: 25.0,
            aLat: 42.427, aLng: 23.855,
            bLat: 42.550, bLng: 23.703
        )
        #expect(dist > 50_000)
    }

    @Test
    func pointToPolylineDistanceOnCenterline() {
        let dist = pointToPolylineDistance(42.480, 23.800, TRAKIYA_T10.centerline)
        #expect(dist < 50)
    }

    @Test
    func pointToPolylineDistanceEmptyPolyline() {
        #expect(pointToPolylineDistance(42.5, 23.8, []) == .greatestFiniteMagnitude)
    }

    @Test
    func pointToPolylineDistanceSinglePoint() {
        let poly: [[Double]] = [[42.5, 23.8]]
        let dist = pointToPolylineDistance(42.5, 23.801, poly)
        #expect(dist < 100)
    }

    @Test
    func projectOntoPolylineAtStart() {
        let proj = projectOntoPolyline(42.427, 23.855, TRAKIYA_T10.centerline)
        #expect(proj < 100)
    }

    @Test
    func projectOntoPolylineAtEnd() {
        let proj = projectOntoPolyline(42.550, 23.703, TRAKIYA_T10.centerline)
        let totalLength = computePolylineLength(TRAKIYA_T10.centerline)
        #expect(approxEqual(proj, totalLength, tol: totalLength * 0.05))
    }

    @Test
    func projectOntoPolylineAtMidpoint() {
        let mid = TRAKIYA_T10.centerline[3] // [42.510, 23.770]
        let proj = projectOntoPolyline(mid[0], mid[1], TRAKIYA_T10.centerline)
        let totalLength = computePolylineLength(TRAKIYA_T10.centerline)
        #expect(proj > totalLength * 0.3)
        #expect(proj < totalLength * 0.7)
    }

    @Test
    func projectPointOntoPolylineEmptyReturnsNil() {
        #expect(projectPointOntoPolyline(42.5, 23.8, []) == nil)
    }

    @Test
    func projectPointOntoPolylineSinglePointReturnsNil() {
        #expect(projectPointOntoPolyline(42.5, 23.8, [[42.5, 23.8]]) == nil)
    }

    @Test
    func projectPointOntoPolylineAtVertex() throws {
        let polyline: [[Double]] = [[42.0, 23.0], [42.0, 24.0]]
        let proj = try #require(projectPointOntoPolyline(42.0, 23.0, polyline))
        #expect(approxEqual(proj.lat, 42.0, tol: 1e-6))
        #expect(approxEqual(proj.lng, 23.0, tol: 1e-6))
        #expect(proj.distanceFromLineM < 1.0)
        #expect(approxEqual(proj.bearing, 90.0, tol: 1.0))
    }

    @Test
    func projectPointOntoPolylinePerpendicular() throws {
        let polyline: [[Double]] = [[42.0, 23.0], [42.0, 24.0]]
        let proj = try #require(projectPointOntoPolyline(42.001, 23.5, polyline))
        #expect(approxEqual(proj.lat, 42.0, tol: 1e-4))
        #expect(approxEqual(proj.lng, 23.5, tol: 1e-4))
        #expect(approxEqual(proj.distanceFromLineM, 111.0, tol: 5.0))
        #expect(approxEqual(proj.bearing, 90.0, tol: 1.0))
    }

    @Test
    func projectPointOntoPolylineClampsPastEnd() throws {
        let polyline: [[Double]] = [[42.0, 23.0], [42.0, 24.0]]
        let proj = try #require(projectPointOntoPolyline(42.0, 25.0, polyline))
        #expect(approxEqual(proj.lat, 42.0, tol: 1e-6))
        #expect(approxEqual(proj.lng, 24.0, tol: 1e-6))
    }

    @Test
    func projectPointOntoPolylinePicksNearestSegment() throws {
        let polyline: [[Double]] = [
            [42.0, 23.0],
            [42.0, 24.0],
            [41.0, 24.0]
        ]
        let proj = try #require(projectPointOntoPolyline(41.5, 24.5, polyline))
        #expect(approxEqual(proj.lat, 41.5, tol: 1e-3))
        #expect(approxEqual(proj.lng, 24.0, tol: 1e-3))
        #expect(approxEqual(proj.bearing, 180.0, tol: 1.0))
    }

    @Test
    func bearingDueEast() {
        #expect(approxEqual(bearingBetween(42.0, 23.0, 42.0, 24.0), 90.0, tol: 1.0))
    }

    @Test
    func bearingDueNorth() {
        #expect(approxEqual(bearingBetween(42.0, 23.0, 43.0, 23.0), 0.0, tol: 1.0))
    }

    @Test
    func bearingDueSouth() {
        #expect(approxEqual(bearingBetween(43.0, 23.0, 42.0, 23.0), 180.0, tol: 1.0))
    }

    @Test
    func bearingDueWest() {
        #expect(approxEqual(bearingBetween(42.0, 24.0, 42.0, 23.0), 270.0, tol: 1.0))
    }

    @Test
    func bearingDifferenceZero() {
        #expect(approxEqual(bearingDifference(90.0, 90.0), 0.0, tol: 0.01))
    }

    @Test
    func bearingDifferenceWrapAround() {
        #expect(approxEqual(bearingDifference(10.0, 350.0), 20.0, tol: 0.01))
    }

    @Test
    func bearingDifferenceOpposite() {
        #expect(approxEqual(bearingDifference(0.0, 180.0), 180.0, tol: 0.01))
    }

    @Test
    func bearingDifferenceSymmetric() {
        #expect(approxEqual(
            bearingDifference(30.0, 60.0),
            bearingDifference(60.0, 30.0),
            tol: 0.01
        ))
    }

    @Test
    func directionToBearingAllCardinals() {
        #expect(directionToBearing("north") == 0.0)
        #expect(directionToBearing("east") == 90.0)
        #expect(directionToBearing("south") == 180.0)
        #expect(directionToBearing("west") == 270.0)
    }

    @Test
    func directionToBearingUnknownReturnsNil() {
        // Swift port returns Optional instead of throwing — same intent
        // (caller falls back to polyline-derived bearing), idiomatic Swift.
        #expect(directionToBearing("northeast") == nil)
    }

    @Test
    func polylineBearingTrakiyaIsNorthwest() throws {
        let bearing = try #require(polylineBearing(TRAKIYA_T10.centerline))
        #expect(bearing > 290 && bearing < 340, "Bearing should be NW, got \(bearing)")
    }

    @Test
    func polylineBearingHemusIsNortheast() throws {
        let bearing = try #require(polylineBearing(HEMUS_H12.centerline))
        #expect(bearing > 50 && bearing < 90, "Bearing should be NE, got \(bearing)")
    }

    @Test
    func polylineBearingTooShortReturnsNil() {
        #expect(polylineBearing([[42.0, 23.0]]) == nil)
    }

    private func computePolylineLength(_ polyline: [[Double]]) -> Double {
        var total = 0.0
        for i in 0..<(polyline.count - 1) {
            total += haversineDistance(
                polyline[i][0], polyline[i][1],
                polyline[i + 1][0], polyline[i + 1][1]
            )
        }
        return total
    }
}

/// Floating-point near-equality. Swift Testing has no built-in `accuracy:`
/// equivalent of `XCTAssertEqual(_:_:accuracy:)`; this is the project-wide
/// shorthand used in `#expect(...)` calls.
func approxEqual(_ a: Double, _ b: Double, tol: Double) -> Bool {
    abs(a - b) <= tol
}
