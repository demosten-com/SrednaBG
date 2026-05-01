// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import SrednaBGCore

/// Battery-friendly GPS cadence. Mirrors the three-tier scheme in
/// `LocationTrackingService.kt`: tight inside a zone, medium near one,
/// loose far away. Pure logic, no CoreLocation deps.
public enum AdaptiveLocationCadence {
    public static let inZoneIntervalMs: Int = 1000
    public static let nearZoneIntervalMs: Int = 2000
    public static let farIntervalMs: Int = 5000
    public static let nearZoneDistanceM: Double = 2000

    /// Suggested update interval, in milliseconds.
    public static func intervalMs(
        for state: ZoneState,
        position: GpsPoint?,
        zones: [Zone]
    ) -> Int {
        switch state {
        case .inZone, .exiting:
            return inZoneIntervalMs
        case .outside:
            guard let position else { return farIntervalMs }
            let near = zones.contains { zone in
                RoadMatcher.distanceToZoneStart(position, zone) < nearZoneDistanceM
                    || RoadMatcher.distanceToZoneEnd(position, zone) < nearZoneDistanceM
            }
            return near ? nearZoneIntervalMs : farIntervalMs
        }
    }
}
