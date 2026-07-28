// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

/// 0xAARRGGBB packed colors matching Android (`Int32` to fit signed Int range).
public let zoneColorGreen: Int32 = Int32(bitPattern: 0xFF66BB6A)
public let zoneColorYellow: Int32 = Int32(bitPattern: 0xFFFDD835)
public let zoneColorRed: Int32 = Int32(bitPattern: 0xFFEF5350)

/// The colour of "no verdict" — used for `ZoneState.Unmeasured`, where we know
/// the driver is inside an average-speed zone but never saw the entry. Green /
/// amber / red *is* the verdict, so rendering any of them there would claim
/// knowledge we do not have. Mirrors Android's `ZONE_COLOR_NEUTRAL`.
public let zoneColorNeutral: Int32 = Int32(bitPattern: 0xFF9E9E9E)

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
