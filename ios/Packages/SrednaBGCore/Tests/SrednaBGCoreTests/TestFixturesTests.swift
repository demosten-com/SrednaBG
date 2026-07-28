// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Testing
@testable import SrednaBGCore

/// Tests for the fixture helpers themselves.
///
/// `pointOnApproach` decides where every "a car genuinely driving this zone"
/// trace begins, so the entry-provenance suite's verdicts rest on it: if it
/// silently stopped extrapolating *backwards* down the approach road, those
/// tests would keep passing while asserting something else entirely (a drive
/// that starts at arc 0 is witnessed either way). Assert it directly rather than
/// only through `collectAlongCenterline`.
///
/// Mirrors the Kotlin `TestFixturesTest`.
@Suite("TestFixtures")
struct TestFixturesTests {

    @Test func pointOnApproachPlacesANegativeArcBehindTheZoneStart() {
        let zone = TRAKIYA_T10
        let heading = localPolylineBearing(zone.centerline, 0, RoadMatcher.localBearingWindowM)!
        let v0 = zone.centerline[0]

        let at = pointOnApproach(zone, -100, heading)

        // 100 m from the first vertex…
        #expect(abs(haversineDistance(at[0], at[1], v0[0], v0[1]) - 100) < 1,
                "A -100 m arc must sit 100 m from the centerline start")
        // …on the far side of it, i.e. the bearing from there to the start is the
        // direction of travel, not its reverse.
        #expect(bearingDifference(bearingBetween(at[0], at[1], v0[0], v0[1]), heading) < 1,
                "The approach point must lie behind the start, heading into the zone")
        // And the projection of an approach point onto the centerline clamps to
        // arc 0 — the property entry provenance is built on.
        #expect(arcLengthOnPolyline(at[0], at[1], zone.centerline) < 0.5,
                "An approach point must project to arc ~0")
    }

    @Test func pointOnApproachDefersToPointAtArcLengthForNonNegativeArcs() {
        let zone = TRAKIYA_T10
        let heading = polylineBearing(zone.centerline)!
        for arc in [0.0, 250.0, 5_000.0] {
            #expect(pointOnApproach(zone, arc, heading) == pointAtArcLength(zone.centerline, arc),
                    "Arc \(arc) is on the line, so it must come straight from pointAtArcLength")
        }
    }

    @Test func pointOnApproachExtrapolatesFromTheStoredFirstVertexJogAndAll() {
        // For the ISSUE-001 fixture the stored first vertex IS the camera, while
        // the geometry immediately doubles back. An approach point must still be
        // measured off that vertex along the real road heading — this is what
        // makes the jog reachable at an arc inside the 100–200 m danger band.
        let zone = jogStartZone()
        let v0 = zone.centerline[0]

        let at = pointOnApproach(zone, -200, jogZoneHeadingDeg)

        #expect(abs(haversineDistance(at[0], at[1], v0[0], v0[1]) - 200) < 1,
                "A -200 m arc must sit 200 m behind the jog zone's camera")
        // And it must project onto the *jog* vertex rather than clamping to arc 0
        // — the whole point of the fixture, and the reason a legitimate approach
        // to i3-02-north lands inside the 100–200 m danger band instead of at 0.
        #expect(abs(arcLengthOnPolyline(at[0], at[1], zone.centerline) - 121) < 2,
                "An approach point must snap to the far end of the backwards jog")
    }

    @Test func jogStartZoneCenterlineEndsExactlyAtTheZoneEnd() {
        let zone = jogStartZone()
        let last = zone.centerline[zone.centerline.count - 1]
        #expect(haversineDistance(last[0], last[1], zone.end.lat, zone.end.lng) < 1,
                "centerline.last and zone.end must agree, or the endpoint checks drift")
    }
}
