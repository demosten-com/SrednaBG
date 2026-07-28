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

    /// Half-width (metres) of the window the centerline's *local* heading is read
    /// over for `matchDirection`.
    ///
    /// The heading test used to compare the fix course against the zone's
    /// end-to-end bearing, which on a long zone is meaningless locally: the A3
    /// Струма motorway passes within 15 m of the I-1 centerline at the Кочериново
    /// interchange on a heading 43–45° off `i1-02-north`'s end-to-end bearing —
    /// inside `directionToleranceDeg` — while being 48–57° off the road's *local*
    /// heading there. That let motorway traffic false-match the I-1 zone.
    ///
    /// 150 m is long enough to smooth out vertex noise and the backwards endpoint
    /// jogs present in the stored geometry (≤122 m), short enough to track the
    /// real curvature of the road. Mirrors Kotlin `LOCAL_BEARING_WINDOW_M`.
    public static let localBearingWindowM = 150.0

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

    /// Does `point`'s course run *with* `zone` where the point sits on it?
    ///
    /// Compares against the centerline's local heading (`localBearingWindowM`),
    /// not its end-to-end bearing, so a road that crosses or runs alongside the
    /// zone is rejected on its own heading rather than on the zone's average one.
    /// Degenerate centerlines (<2 points) fall back to the cardinal
    /// `Zone.direction`.
    public static func matchDirection(
        _ point: GpsPoint,
        _ zone: Zone,
        tolerance: Double = directionToleranceDeg
    ) -> Bool {
        guard let position = positionOnPolyline(point.lat, point.lng, zone.centerline) else {
            guard let cardinal = directionToBearing(zone.direction) else { return false }
            return bearingDifference(point.bearing, cardinal) <= tolerance
        }
        return matchesLocalDirection(point, zone, position, tolerance: tolerance)
    }

    /// `matchDirection` for a caller that already projected the point onto the centerline.
    public static func matchesLocalDirection(
        _ point: GpsPoint,
        _ zone: Zone,
        _ position: PolylinePosition,
        tolerance: Double = directionToleranceDeg
    ) -> Bool {
        guard let local = localPolylineBearing(
            zone.centerline, position.arcLengthM, localBearingWindowM
        ) else { return false }
        return bearingDifference(point.bearing, local) <= tolerance
    }

    public static func findMatchingZone(_ point: GpsPoint, _ zones: [Zone]) -> Zone? {
        // Project onto each centerline once and reuse that projection for the
        // on-road band test, the local-heading test, and the nearest-zone
        // tie-break — each used to re-walk every centerline on its own.
        //
        // Not a claim that a fix now costs one walk per zone: matchesLocalDirection
        // still walks inside localPolylineBearing (a polylineLengthMeters plus two
        // pointAtArcLength lookups). What changed is that those walks are now
        // short-circuited to the zones already inside the on-road band — normally
        // zero or one of ~72 — instead of running unconditionally for every zone.
        zones
            .compactMap { zone -> (Zone, PolylinePosition)? in
                guard let position = positionOnPolyline(point.lat, point.lng, zone.centerline)
                else { return nil }
                return (zone, position)
            }
            .filter { zone, position in
                position.distanceFromLineM <= maxOnRoadDistanceM(zone) &&
                    matchesLocalDirection(point, zone, position)
            }
            .min { $0.1.distanceFromLineM < $1.1.distanceFromLineM }
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
