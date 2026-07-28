// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

object RoadMatcher {

    private const val DEFAULT_MAX_DISTANCE_M = 100.0
    private const val MOTORWAY_MAX_DISTANCE_M = 150.0

    /** Heading-match tolerance (degrees) between the fix bearing and the zone's centerline. */
    const val DIRECTION_TOLERANCE_DEG = 45.0

    /**
     * Half-width (metres) of the window the centerline's *local* heading is read
     * over for [matchDirection].
     *
     * The heading test used to compare the fix course against the zone's
     * end-to-end bearing, which on a long zone is meaningless locally: the A3
     * Струма motorway passes within 15 m of the I-1 centerline at the Кочериново
     * interchange on a heading 43–45° off `i1-02-north`'s end-to-end bearing —
     * inside [DIRECTION_TOLERANCE_DEG] — while being 48–57° off the road's
     * *local* heading there. That let motorway traffic false-match the I-1 zone.
     *
     * 150 m is long enough to smooth out vertex noise and the backwards endpoint
     * jogs present in the stored geometry (≤122 m), short enough to track the
     * real curvature of the road.
     */
    const val LOCAL_BEARING_WINDOW_M = 150.0

    fun isOnRoad(point: GpsPoint, zone: Zone, maxDistance: Double = maxOnRoadDistanceM(zone)): Boolean {
        if (zone.centerline.size < 2) return false
        return pointToPolylineDistance(point.lat, point.lng, zone.centerline) <= maxDistance
    }

    /**
     * The on-road band (metres) for [zone] — wider on motorways. Public so a
     * caller that already has the centerline distance (e.g. the in-zone off-road
     * check) can compare against it directly instead of recomputing the distance
     * inside [isOnRoad].
     */
    fun maxOnRoadDistanceM(zone: Zone): Double {
        return if (isMotorway(zone)) MOTORWAY_MAX_DISTANCE_M else DEFAULT_MAX_DISTANCE_M
    }

    /**
     * Does [point]'s course run *with* [zone] where the point sits on it?
     *
     * Compares against the centerline's local heading ([LOCAL_BEARING_WINDOW_M]),
     * not its end-to-end bearing, so a road that crosses or runs alongside the
     * zone is rejected on its own heading rather than on the zone's average one.
     * Degenerate centerlines (<2 points) fall back to the cardinal [Zone.direction].
     */
    fun matchDirection(point: GpsPoint, zone: Zone, tolerance: Double = DIRECTION_TOLERANCE_DEG): Boolean {
        val position = positionOnPolyline(point.lat, point.lng, zone.centerline)
            ?: return directionToBearing(zone.direction)
                ?.let { bearingDifference(point.bearing, it) <= tolerance }
                ?: false
        return matchesLocalDirection(point, zone, position, tolerance)
    }

    /** [matchDirection] for a caller that already projected the point onto the centerline. */
    fun matchesLocalDirection(
        point: GpsPoint,
        zone: Zone,
        position: PolylinePosition,
        tolerance: Double = DIRECTION_TOLERANCE_DEG,
    ): Boolean {
        val local = localPolylineBearing(zone.centerline, position.arcLengthM, LOCAL_BEARING_WINDOW_M)
            ?: return false
        return bearingDifference(point.bearing, local) <= tolerance
    }

    fun findMatchingZone(point: GpsPoint, zones: List<Zone>): Zone? {
        // Project onto each centerline once and reuse that projection for the
        // on-road band test, the local-heading test, and the nearest-zone
        // tie-break — each used to re-walk every centerline on its own.
        //
        // Not a claim that a fix now costs one walk per zone: matchesLocalDirection
        // still walks inside localPolylineBearing (a polylineLengthMeters plus two
        // pointAtArcLength lookups). What changed is that those walks are now
        // short-circuited to the zones already inside the on-road band — normally
        // zero or one of ~72 — instead of running unconditionally for every zone.
        return zones.asSequence()
            .mapNotNull { zone ->
                positionOnPolyline(point.lat, point.lng, zone.centerline)?.let { zone to it }
            }
            .filter { (zone, position) ->
                position.distanceFromLineM <= maxOnRoadDistanceM(zone) &&
                    matchesLocalDirection(point, zone, position)
            }
            .minByOrNull { (_, position) -> position.distanceFromLineM }
            ?.first
    }

    fun distanceToZoneStart(point: GpsPoint, zone: Zone): Double {
        return haversineDistance(point.lat, point.lng, zone.start.lat, zone.start.lng)
    }

    fun distanceToZoneEnd(point: GpsPoint, zone: Zone): Double {
        return haversineDistance(point.lat, point.lng, zone.end.lat, zone.end.lng)
    }

    fun distanceToCenterline(point: GpsPoint, zone: Zone): Double {
        if (zone.centerline.size < 2) return Double.MAX_VALUE
        return pointToPolylineDistance(point.lat, point.lng, zone.centerline)
    }

    private fun isMotorway(zone: Zone): Boolean {
        return zone.road.startsWith("АМ ") || zone.road.startsWith("AM ")
    }
}
