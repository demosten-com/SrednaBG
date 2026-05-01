// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

public enum RoadMatcher {
    public static let defaultMaxDistanceM = 100.0
    public static let motorwayMaxDistanceM = 150.0

    public static func isOnRoad(
        _ point: GpsPoint,
        _ zone: Zone,
        maxDistance: Double? = nil
    ) -> Bool {
        if zone.centerline.count < 2 { return false }
        let limit = maxDistance ?? defaultMaxDistance(for: zone)
        return pointToPolylineDistance(point.lat, point.lng, zone.centerline) <= limit
    }

    public static func matchDirection(
        _ bearing: Double,
        _ zone: Zone,
        tolerance: Double = 45.0
    ) -> Bool {
        let zoneBearing: Double
        if zone.centerline.count >= 2, let pb = polylineBearing(zone.centerline) {
            zoneBearing = pb
        } else if let cardinal = directionToBearing(zone.direction) {
            zoneBearing = cardinal
        } else {
            return false
        }
        return bearingDifference(bearing, zoneBearing) <= tolerance
    }

    public static func findMatchingZone(_ point: GpsPoint, _ zones: [Zone]) -> Zone? {
        zones
            .filter { isOnRoad(point, $0) && matchDirection(point.bearing, $0) }
            .min { a, b in
                pointToPolylineDistance(point.lat, point.lng, a.centerline)
                    < pointToPolylineDistance(point.lat, point.lng, b.centerline)
            }
    }

    public static func distanceToZoneStart(_ point: GpsPoint, _ zone: Zone) -> Double {
        haversineDistance(point.lat, point.lng, zone.start.lat, zone.start.lng)
    }

    public static func distanceToZoneEnd(_ point: GpsPoint, _ zone: Zone) -> Double {
        haversineDistance(point.lat, point.lng, zone.end.lat, zone.end.lng)
    }

    public static func distanceToCenterline(_ point: GpsPoint, _ zone: Zone) -> Double {
        if zone.centerline.count < 2 { return .greatestFiniteMagnitude }
        return pointToPolylineDistance(point.lat, point.lng, zone.centerline)
    }

    private static func defaultMaxDistance(for zone: Zone) -> Double {
        isMotorway(zone) ? motorwayMaxDistanceM : defaultMaxDistanceM
    }

    private static func isMotorway(_ zone: Zone) -> Bool {
        // Cyrillic "АМ " (Autoмагистрала) or Latin "AM ".
        zone.road.hasPrefix("АМ ") || zone.road.hasPrefix("AM ")
    }
}
