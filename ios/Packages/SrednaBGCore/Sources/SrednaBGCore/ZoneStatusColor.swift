// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

/// 0xAARRGGBB packed colors matching Android (`Int32` to fit signed Int range).
public let zoneColorGreen: Int32 = Int32(bitPattern: 0xFF66BB6A)
public let zoneColorYellow: Int32 = Int32(bitPattern: 0xFFFDD835)
public let zoneColorRed: Int32 = Int32(bitPattern: 0xFFEF5350)

/// Status traffic light: red if the running average is over the limit, yellow
/// if the current instantaneous speed exceeds the limit (recoverable), green
/// otherwise. Uses the **car** limit deliberately — this matches Android. Pass
/// the vehicle-aware limit upstream if you need per-vehicle coloring.
public func zoneStatusColor(state: ZoneState.InZone, currentSpeedKmh: Double?) -> Int32 {
    if state.speedStatus.isOverLimit { return zoneColorRed }
    if let speed = currentSpeedKmh, speed > Double(state.zone.speedLimits.car) {
        return zoneColorYellow
    }
    return zoneColorGreen
}
