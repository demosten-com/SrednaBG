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

    fun matchDirection(bearing: Double, zone: Zone, tolerance: Double = DIRECTION_TOLERANCE_DEG): Boolean {
        val zoneBearing = if (zone.centerline.size >= 2) {
            polylineBearing(zone.centerline)
        } else {
            directionToBearing(zone.direction) ?: return false
        }
        return bearingDifference(bearing, zoneBearing) <= tolerance
    }

    fun findMatchingZone(point: GpsPoint, zones: List<Zone>): Zone? {
        // Compute the point-to-centerline distance once per zone and reuse it for
        // both the on-road band check and the nearest-zone selection (it was
        // previously computed twice — in isOnRoad's filter and again in minByOrNull).
        return zones.asSequence()
            .filter { zone -> zone.centerline.size >= 2 }
            .map { zone -> zone to pointToPolylineDistance(point.lat, point.lng, zone.centerline) }
            .filter { (zone, dist) -> dist <= maxOnRoadDistanceM(zone) && matchDirection(point.bearing, zone) }
            .minByOrNull { (_, dist) -> dist }
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
