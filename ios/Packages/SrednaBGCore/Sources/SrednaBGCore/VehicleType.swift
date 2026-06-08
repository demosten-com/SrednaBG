// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

// Driver-selected vehicle type. `ZoneDetector.update(_:vehicleType:)` uses it to
// pick the applicable speed limit. The Kotlin core matches this (see
// `android/core/.../VehicleType.kt`).

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
