// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Testing
@testable import SrednaBGCore

/// Kept in lockstep with `android/core/.../VehicleTypeTest.kt` — the two cores
/// must resolve identical limits and setting strings.
@Suite("VehicleType")
struct VehicleTypeTests {

    private let motorway = SpeedLimits(car: 140, truck: 90, bus: 100, motorcycle: 130)
    private let national = SpeedLimits(car: 90, truck: 80, bus: 80)

    @Test
    func eachTypePicksItsOwnLimit() {
        #expect(VehicleType.car.limit(motorway) == 140)
        #expect(VehicleType.truck.limit(motorway) == 90)
        #expect(VehicleType.bus.limit(motorway) == 100)
        #expect(VehicleType.motorcycle.limit(motorway) == 130)
    }

    @Test
    func motorcycleFallsBackToCarWhenUnset() {
        #expect(VehicleType.motorcycle.limit(national) == 90)
    }

    /// `.bus` is the whole `BE,C1,C1E,D,D1,D1E,DE` licence class, so a car towing
    /// a trailer and a 3.5–7.5 t truck resolve it too — that is why the Settings
    /// row names the class, not just buses. Pins that it stays distinct from the
    /// car limit, which is the value those drivers would otherwise get.
    @Test
    func busIsTheWholeBEC1DLicenceClassAndDiffersFromCar() {
        #expect(VehicleType.bus.limit(motorway) == 100)
        #expect(VehicleType.bus.limit(national) == 80)
        #expect(VehicleType.bus.limit(motorway) != VehicleType.car.limit(motorway))
    }

    /// The raw values are the persisted setting strings and are shared verbatim
    /// with Android's `VehicleType.fromSetting`.
    @Test
    func rawValuesMatchTheAndroidSettingTokens() {
        #expect(VehicleType.car.rawValue == "car")
        #expect(VehicleType.truck.rawValue == "truck")
        #expect(VehicleType.bus.rawValue == "bus")
        #expect(VehicleType.motorcycle.rawValue == "motorcycle")
    }

    @Test
    func everyCaseRoundTripsThroughItsRawValue() {
        for type in VehicleType.allCases {
            #expect(VehicleType(rawValue: type.rawValue) == type)
        }
        #expect(VehicleType.allCases.count == 4)
    }

    @Test
    func unknownRawValueDoesNotDecode() {
        #expect(VehicleType(rawValue: "bogus") == nil)
        // The removed car-with-trailer type must not linger as a live raw value.
        #expect(VehicleType(rawValue: "car_trailer") == nil)
    }
}
