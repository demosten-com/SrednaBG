// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

// Driver-selected vehicle type. `ZoneDetector.update(_:vehicleType:)` uses it to
// pick the applicable speed limit. The Kotlin core matches this (see
// `android/core/.../VehicleType.kt`).

// These map onto BG TOLL's three licence-category classes, NOT onto vehicle
// shapes — see the note on `SpeedLimits` in Models.swift. `bus` is the whole
// `BE,C1,C1E,D,D1,D1E,DE` class, so it is also what a car towing a trailer or a
// 3.5–7.5 t truck selects; the Settings row is labelled for the class rather
// than for buses alone. There is deliberately no separate car-with-trailer
// case: it would be a second enum value resolving an identical limit.
//
// The raw values are the persisted setting strings, shared with Android's
// `VehicleType.setting` — keep the two spellings identical.

public enum VehicleType: String, Sendable, CaseIterable, Codable {
    case car
    case truck
    case bus
    case motorcycle

    public func limit(_ limits: SpeedLimits) -> Int {
        switch self {
        case .car: return limits.car
        case .truck: return limits.truck
        case .bus: return limits.bus
        case .motorcycle: return limits.motorcycle ?? limits.car
        }
    }
}
