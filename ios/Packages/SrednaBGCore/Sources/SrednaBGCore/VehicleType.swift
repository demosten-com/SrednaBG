// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

// iOS bug-fix vs Android: ZoneDetector.update(_:vehicleType:) honors the
// driver's selected vehicle type when looking up the speed limit. Android
// currently hardcodes .car everywhere — TODO to backport.

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
