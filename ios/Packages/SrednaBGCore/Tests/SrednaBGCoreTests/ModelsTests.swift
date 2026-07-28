// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Testing
@testable import SrednaBGCore

@Suite("Models")
struct ModelsTests {

    @Test
    func zoneCreationWithAllFields() {
        let zone = TRAKIYA_T10
        #expect(zone.id == "trakiya-01-west")
        #expect(zone.road == "АМ Тракия")
        #expect(zone.direction == "west")
        #expect(zone.distanceM == 19160)
        #expect(zone.speedLimits.car == 140)
        #expect(zone.centerline.count == 6)
    }

    @Test
    func zoneStateOutsideEqualsItself() {
        #expect(ZoneState.outside == ZoneState.outside)
    }

    @Test
    func zoneStateInZoneHoldsData() {
        let status = SpeedStatus(
            avgSpeed: 130.0,
            maxSpeedForRemainder: 150.0,
            distanceRemaining: 10000.0,
            timeRemaining: 200.0,
            isOverLimit: false
        )
        let inZone = ZoneState.InZone(
            zone: TRAKIYA_T10,
            entryTime: epochBase,
            distanceTraveled: 9160.0,
            speedStatus: status,
            distanceRemaining: 10000.0
        )
        #expect(inZone.zone == TRAKIYA_T10)
        #expect(inZone.avgSpeed == 130.0)
    }

    @Test
    func zoneStateExhaustivePatternMatching() {
        let states: [ZoneState] = [
            .outside,
            .inZone(.init(
                zone: TRAKIYA_T10,
                entryTime: epochBase,
                distanceTraveled: 0,
                speedStatus: SpeedStatus(
                    avgSpeed: 0,
                    maxSpeedForRemainder: 140,
                    distanceRemaining: 19160,
                    timeRemaining: 492,
                    isOverLimit: false
                ),
                distanceRemaining: 19160
            )),
            .unmeasured(.init(zone: TRAKIYA_T10, distanceRemaining: 8000)),
            .exiting(.init(zone: TRAKIYA_T10, finalAvgSpeed: 135.0))
        ]
        let names: [String] = states.map { state in
            switch state {
            case .outside: return "outside"
            case .inZone: return "inzone"
            case .unmeasured: return "unmeasured"
            case .exiting: return "exiting"
            }
        }
        #expect(names == ["outside", "inzone", "unmeasured", "exiting"])
    }

    @Test
    func gpsPointConstruction() {
        let point = GpsPoint(lat: 42.5, lng: 23.8, speed: 130.0, timestamp: epochBase, bearing: 270.0)
        #expect(point.lat == 42.5)
        #expect(point.speed == 130.0)
    }

    @Test
    func speedLimitsWithOptionalMotorcycle() {
        let withMoto = SpeedLimits(car: 140, truck: 90, bus: 100, motorcycle: 140)
        #expect(withMoto.motorcycle == 140)

        let withoutMoto = SpeedLimits(car: 90, truck: 80, bus: 80)
        #expect(withoutMoto.motorcycle == nil)
    }

    // Swift-only: enforce Sendable conformance on the public state enum so the
    // GPS-consumer task in ZoneTrackingService can safely publish to MainActor.
    @Test
    func zoneStateIsSendable() {
        func requireSendable<T: Sendable>(_: T.Type) {}
        requireSendable(ZoneState.self)
        requireSendable(GpsPoint.self)
        requireSendable(Zone.self)
        requireSendable(SpeedStatus.self)
    }
}
