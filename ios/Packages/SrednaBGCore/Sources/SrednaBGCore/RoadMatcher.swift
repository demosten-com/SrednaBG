// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

public enum RoadMatcher {
    public static let defaultMaxDistanceM = 100.0
    public static let motorwayMaxDistanceM = 150.0

    /// Heading-match tolerance (degrees) between the fix bearing and the zone's centerline.
    public static let directionToleranceDeg = 45.0

    public static func isOnRoad(
        _ point: GpsPoint,
        _ zone: Zone,
        maxDistance: Double? = nil
    ) -> Bool {
        if zone.centerline.count < 2 { return false }
        let limit = maxDistance ?? maxOnRoadDistanceM(zone)
        return pointToPolylineDistance(point.lat, point.lng, zone.centerline) <= limit
    }

    /// The on-road band (metres) for `zone` — wider on motorways. Public so a
    /// caller that already has the centerline distance (e.g. the in-zone off-road
    /// check) can compare against it directly instead of recomputing the distance
    /// inside `isOnRoad`. Mirrors Android's `maxOnRoadDistanceM`.
    public static func maxOnRoadDistanceM(_ zone: Zone) -> Double {
        isMotorway(zone) ? motorwayMaxDistanceM : defaultMaxDistanceM
    }

    public static func matchDirection(
        _ bearing: Double,
        _ zone: Zone,
        tolerance: Double = directionToleranceDeg
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
        // Compute the point-to-centerline distance once per zone and reuse it for
        // both the on-road band check and the nearest-zone selection (it was
        // previously computed in isOnRoad's filter and again in the min comparator).
        zones
            .filter { $0.centerline.count >= 2 }
            .map { ($0, pointToPolylineDistance(point.lat, point.lng, $0.centerline)) }
            .filter { zone, dist in dist <= maxOnRoadDistanceM(zone) && matchDirection(point.bearing, zone) }
            .min { $0.1 < $1.1 }
            .map { $0.0 }
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

    private static func isMotorway(_ zone: Zone) -> Bool {
        // Cyrillic "АМ " (Autoмагистрала) or Latin "AM ".
        zone.road.hasPrefix("АМ ") || zone.road.hasPrefix("AM ")
    }
}
