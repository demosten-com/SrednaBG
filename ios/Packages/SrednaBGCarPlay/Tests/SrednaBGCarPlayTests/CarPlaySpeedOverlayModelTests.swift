// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCarPlay

import Foundation
import Testing
@testable import SrednaBGCarPlay
import SrednaBGCore

@Suite("CarPlaySpeedOverlayModel")
struct CarPlaySpeedOverlayModelTests {

    // MARK: - Fixtures

    private static let labels = CarPlayLabels(
        overLimit: "OVER",
        withinLimit: "WITHIN",
        nowSpeedFormat: "Now %@ km/h",
        currentSpeedLabel: "current",
        avgSpeedLabel: "avg",
        remaining: "remaining",
        speedLimit: "limit",
        finalAvgSpeedFormat: "final %@ km/h",
        zoneCompleteTitle: "COMPLETE",
        trackingOutsideTitle: "OUTSIDE",
        notTrackingTitle: "OFF",
        tapToStartHint: "TAP"
    )

    private static func fixtureZone() -> Zone {
        Zone(
            id: "zone-1",
            road: "AM Trakia",
            roadLatin: nil,
            direction: "east",
            description: "fixture",
            start: ZoneEndpoint(lat: 42.0, lng: 24.0, kmMarker: nil, settlement: nil, settlementLatin: nil),
            end: ZoneEndpoint(lat: 42.1, lng: 24.1, kmMarker: nil, settlement: nil, settlementLatin: nil),
            distanceM: 10_000,
            speedLimits: SpeedLimits(car: 120, truck: 100, bus: 110, motorcycle: nil),
            centerline: [[42.0, 24.0], [42.1, 24.1]],
            source: "test",
            lastVerified: "2026-04-24"
        )
    }

    private static func overSpeed(status: SpeedStatus) -> Bool { status.isOverLimit }

    // MARK: - notTracking

    @Test("notTrackingBlanksEverythingAndShowsHint")
    func notTrackingBlanksEverythingAndShowsHint() {
        let model = CarPlaySpeedOverlayModel.from(
            isTracking: false,
            state: .outside,
            currentSpeedKmh: nil,
            vehicleType: .car,
            labels: Self.labels
        )
        #expect(model.mode == .notTracking)
        #expect(model.heroSpeedText == "--")
        #expect(model.smallSpeedText == nil)
        #expect(model.limitText == nil)
        #expect(model.distanceText == nil)
        #expect(model.statusLabel == "TAP")
        #expect(model.packedStatusColor == 0)
    }

    // MARK: - outside

    @Test("outsideShowsCurrentSpeedHero")
    func outsideShowsCurrentSpeedHero() {
        let model = CarPlaySpeedOverlayModel.from(
            isTracking: true,
            state: .outside,
            currentSpeedKmh: 72.4,
            vehicleType: .car,
            labels: Self.labels
        )
        #expect(model.mode == .outside)
        #expect(model.heroSpeedText == "72")     // rounded
        #expect(model.heroSubtitle == "current")
        #expect(model.smallSpeedText == nil)
        #expect(model.limitText == nil)
        #expect(model.distanceText == nil)
        #expect(model.statusLabel == "OUTSIDE")
    }

    @Test("outsideWithNoFixShowsDash")
    func outsideWithNoFixShowsDash() {
        let model = CarPlaySpeedOverlayModel.from(
            isTracking: true,
            state: .outside,
            currentSpeedKmh: nil,
            vehicleType: .car,
            labels: Self.labels
        )
        #expect(model.heroSpeedText == "--")
    }

    // MARK: - inZone

    @Test("inZoneWithinLimitShowsGreenStatus")
    func inZoneWithinLimitShowsGreenStatus() {
        let zone = Self.fixtureZone()
        let status = SpeedStatus(
            avgSpeed: 110,
            maxSpeedForRemainder: 130,
            distanceRemaining: 5_000,
            timeRemaining: 150,
            isOverLimit: false
        )
        let inZone = ZoneState.InZone(
            zone: zone,
            entryTime: 0,
            distanceTraveled: 5_000,
            avgSpeed: 110,
            speedStatus: status,
            distanceRemaining: 5_000
        )
        let model = CarPlaySpeedOverlayModel.from(
            isTracking: true,
            state: .inZone(inZone),
            currentSpeedKmh: 115,
            vehicleType: .car,
            labels: Self.labels
        )
        #expect(model.mode == .inZone)
        #expect(model.heroSpeedText == "110")
        #expect(model.heroSubtitle == "avg")
        #expect(model.smallSpeedText == "115")
        #expect(model.smallSubtitle == "current")
        #expect(model.limitText == "120")  // car limit from fixture
        #expect(model.distanceText == "5.0 km")
        #expect(model.distanceSubtitle == "remaining")
        #expect(model.statusLabel == "WITHIN")
        // green when under limit
        #expect(model.packedStatusColor == zoneColorGreen)
    }

    @Test("inZoneOverLimitShowsRedStatus")
    func inZoneOverLimitShowsRedStatus() {
        let zone = Self.fixtureZone()
        let status = SpeedStatus(
            avgSpeed: 130,
            maxSpeedForRemainder: 100,
            distanceRemaining: 3_000,
            timeRemaining: 90,
            isOverLimit: true
        )
        let inZone = ZoneState.InZone(
            zone: zone,
            entryTime: 0,
            distanceTraveled: 7_000,
            avgSpeed: 130,
            speedStatus: status,
            distanceRemaining: 3_000
        )
        let model = CarPlaySpeedOverlayModel.from(
            isTracking: true,
            state: .inZone(inZone),
            currentSpeedKmh: 135,
            vehicleType: .car,
            labels: Self.labels
        )
        #expect(model.statusLabel == "OVER")
        #expect(model.packedStatusColor == zoneColorRed)
        #expect(model.distanceText == "3.0 km")
    }

    @Test("inZoneUsesVehicleTypeLimit")
    func inZoneUsesVehicleTypeLimit() {
        let zone = Self.fixtureZone()
        let status = SpeedStatus(
            avgSpeed: 90,
            maxSpeedForRemainder: 110,
            distanceRemaining: 2_000,
            timeRemaining: 80,
            isOverLimit: false
        )
        let inZone = ZoneState.InZone(
            zone: zone,
            entryTime: 0,
            distanceTraveled: 8_000,
            avgSpeed: 90,
            speedStatus: status,
            distanceRemaining: 2_000
        )
        let truckModel = CarPlaySpeedOverlayModel.from(
            isTracking: true,
            state: .inZone(inZone),
            currentSpeedKmh: 92,
            vehicleType: .truck,
            labels: Self.labels
        )
        #expect(truckModel.limitText == "100")   // truck limit from fixture
        let busModel = CarPlaySpeedOverlayModel.from(
            isTracking: true,
            state: .inZone(inZone),
            currentSpeedKmh: 92,
            vehicleType: .bus,
            labels: Self.labels
        )
        #expect(busModel.limitText == "110")
    }

    @Test("inZoneWithNilSpeedsRendersDashes")
    func inZoneWithNilSpeedsRendersDashes() {
        let zone = Self.fixtureZone()
        let status = SpeedStatus(
            avgSpeed: nil,
            maxSpeedForRemainder: 120,
            distanceRemaining: 1_000,
            timeRemaining: 60,
            isOverLimit: false
        )
        let inZone = ZoneState.InZone(
            zone: zone,
            entryTime: 0,
            distanceTraveled: 9_000,
            avgSpeed: nil,
            speedStatus: status,
            distanceRemaining: 1_000
        )
        let model = CarPlaySpeedOverlayModel.from(
            isTracking: true,
            state: .inZone(inZone),
            currentSpeedKmh: nil,
            vehicleType: .car,
            labels: Self.labels
        )
        #expect(model.heroSpeedText == "--")
        #expect(model.smallSpeedText == "--")
        #expect(model.limitText == "120")
        #expect(model.distanceText == "1.0 km")
    }

    // MARK: - exiting

    @Test("exitingShowsFinalRecap")
    func exitingShowsFinalRecap() {
        let zone = Self.fixtureZone()
        let exiting = ZoneState.Exiting(zone: zone, finalAvgSpeed: 108.6)
        let model = CarPlaySpeedOverlayModel.from(
            isTracking: true,
            state: .exiting(exiting),
            currentSpeedKmh: 90,
            vehicleType: .car,
            labels: Self.labels
        )
        #expect(model.mode == .exiting)
        #expect(model.heroSpeedText == "109")  // rounded from 108.6
        #expect(model.statusLabel == "final 109 km/h")
        #expect(model.limitText == nil)
        #expect(model.distanceText == nil)
        #expect(model.smallSpeedText == nil)
    }

    @Test("exitingWithNilFinalSpeedFallsBackToDash")
    func exitingWithNilFinalSpeedFallsBackToDash() {
        let zone = Self.fixtureZone()
        let exiting = ZoneState.Exiting(zone: zone, finalAvgSpeed: nil)
        let model = CarPlaySpeedOverlayModel.from(
            isTracking: true,
            state: .exiting(exiting),
            currentSpeedKmh: nil,
            vehicleType: .car,
            labels: Self.labels
        )
        #expect(model.heroSpeedText == "--")
        #expect(model.statusLabel == "final -- km/h")
    }

    // MARK: - formatting

    @Test("formatSpeedHandlesNonFinite")
    func formatSpeedHandlesNonFinite() {
        #expect(CarPlaySpeedOverlayModel.formatSpeed(.nan) == "--")
        #expect(CarPlaySpeedOverlayModel.formatSpeed(.infinity) == "--")
        #expect(CarPlaySpeedOverlayModel.formatSpeed(nil) == "--")
        #expect(CarPlaySpeedOverlayModel.formatSpeed(59.6) == "60")
    }

    @Test("formatDistanceHandlesNegativeAndNonFinite")
    func formatDistanceHandlesNegativeAndNonFinite() {
        #expect(CarPlaySpeedOverlayModel.formatDistance(.nan) == "--")
        #expect(CarPlaySpeedOverlayModel.formatDistance(-5) == "--")
        #expect(CarPlaySpeedOverlayModel.formatDistance(0) == "0.0 km")
        // 12350 m → 12.35 km → "12.3 km" (banker's rounding via %.1f).
        #expect(CarPlaySpeedOverlayModel.formatDistance(12_350) == "12.3 km")
        #expect(CarPlaySpeedOverlayModel.formatDistance(12_360) == "12.4 km")
    }

    @Test("modelEqualityStableAcrossRebuild")
    func modelEqualityStableAcrossRebuild() {
        let a = CarPlaySpeedOverlayModel.from(
            isTracking: true, state: .outside, currentSpeedKmh: 50,
            vehicleType: .car, labels: Self.labels
        )
        let b = CarPlaySpeedOverlayModel.from(
            isTracking: true, state: .outside, currentSpeedKmh: 50,
            vehicleType: .car, labels: Self.labels
        )
        #expect(a == b)
    }
}
