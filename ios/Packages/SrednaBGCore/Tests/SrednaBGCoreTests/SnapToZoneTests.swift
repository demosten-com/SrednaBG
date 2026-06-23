// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Testing
@testable import SrednaBGCore

@Suite("snapToZone")
struct SnapToZoneTests {

    private let rawPoint = GpsPoint(
        lat: 42.5,
        lng: 23.8,
        speed: 130.0,
        timestamp: 1_700_000_000_000,
        bearing: 270.0,
        accuracy: 5.0
    )

    @Test
    func nilPositionReturnsNil() {
        #expect(snapToZone(nil, state: .outside) == nil)
    }

    @Test
    func outsideStateReturnsRawPositionUnchanged() {
        let snapped = snapToZone(rawPoint, state: .outside)
        // Value-type equality replaces Kotlin's reference identity check.
        #expect(snapped == rawPoint)
    }

    @Test
    func exitingStateReturnsRawPositionUnchanged() {
        let state = ZoneState.exiting(.init(zone: TRAKIYA_T10, finalAvgSpeed: 130.0))
        let snapped = snapToZone(rawPoint, state: state)
        #expect(snapped == rawPoint)
    }

    @Test
    func inZoneStateSnapsLatLngToCenterlineAndOverwritesBearing() throws {
        let nearStartRaw = rawPoint.with(lat: 42.428, lng: 23.860, bearing: 12.0)
        let state = ZoneState.inZone(.init(
            zone: TRAKIYA_T10,
            entryTime: nearStartRaw.timestamp,
            distanceTraveled: 0.0,
            speedStatus: SpeedStatus(
                avgSpeed: nil,
                maxSpeedForRemainder: 140.0,
                distanceRemaining: Double(TRAKIYA_T10.distanceM),
                timeRemaining: 0.0,
                isOverLimit: false
            ),
            distanceRemaining: Double(TRAKIYA_T10.distanceM)
        ))

        let snapped = try #require(snapToZone(nearStartRaw, state: state))

        let distFromRaw = haversineDistance(snapped.lat, snapped.lng, nearStartRaw.lat, nearStartRaw.lng)
        #expect(distFromRaw < 600.0, "Snap should be modest, got \(distFromRaw)m")
        let distFromLine = pointToPolylineDistance(snapped.lat, snapped.lng, TRAKIYA_T10.centerline)
        #expect(distFromLine < 1.0, "Snapped point should lie on centerline, got \(distFromLine)m")

        #expect(snapped.bearing >= 290.0 && snapped.bearing <= 340.0,
                "Expected NW bearing, got \(snapped.bearing)")

        #expect(snapped.speed == nearStartRaw.speed)
        #expect(snapped.timestamp == nearStartRaw.timestamp)
        #expect(snapped.accuracy == nearStartRaw.accuracy)
    }

    @Test
    func inZoneStateWithDegenerateCenterlineReturnsRawPosition() {
        let degenerateZone = Zone(
            id: TRAKIYA_T10.id,
            road: TRAKIYA_T10.road,
            roadLatin: TRAKIYA_T10.roadLatin,
            direction: TRAKIYA_T10.direction,
            description: TRAKIYA_T10.description,
            start: TRAKIYA_T10.start,
            end: TRAKIYA_T10.end,
            distanceM: TRAKIYA_T10.distanceM,
            speedLimits: TRAKIYA_T10.speedLimits,
            centerline: [[42.5, 23.8]],
            source: TRAKIYA_T10.source,
            lastVerified: TRAKIYA_T10.lastVerified
        )
        let state = ZoneState.inZone(.init(
            zone: degenerateZone,
            entryTime: rawPoint.timestamp,
            distanceTraveled: 0.0,
            speedStatus: SpeedStatus(
                avgSpeed: nil,
                maxSpeedForRemainder: 140.0,
                distanceRemaining: 0,
                timeRemaining: 0,
                isOverLimit: false
            ),
            distanceRemaining: 0
        ))
        let snapped = snapToZone(rawPoint, state: state)
        #expect(snapped == rawPoint)
    }
}
