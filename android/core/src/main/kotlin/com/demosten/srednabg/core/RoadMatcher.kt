// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

object RoadMatcher {

    private const val DEFAULT_MAX_DISTANCE_M = 100.0
    private const val MOTORWAY_MAX_DISTANCE_M = 150.0

    fun isOnRoad(point: GpsPoint, zone: Zone, maxDistance: Double = defaultMaxDistance(zone)): Boolean {
        if (zone.centerline.size < 2) return false
        return pointToPolylineDistance(point.lat, point.lng, zone.centerline) <= maxDistance
    }

    fun matchDirection(bearing: Double, zone: Zone, tolerance: Double = 45.0): Boolean {
        val zoneBearing = if (zone.centerline.size >= 2) {
            polylineBearing(zone.centerline)
        } else {
            directionToBearing(zone.direction)
        }
        return bearingDifference(bearing, zoneBearing) <= tolerance
    }

    fun findMatchingZone(point: GpsPoint, zones: List<Zone>): Zone? {
        return zones
            .filter { zone -> isOnRoad(point, zone) && matchDirection(point.bearing, zone) }
            .minByOrNull { zone -> pointToPolylineDistance(point.lat, point.lng, zone.centerline) }
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

    private fun defaultMaxDistance(zone: Zone): Double {
        return if (isMotorway(zone)) MOTORWAY_MAX_DISTANCE_M else DEFAULT_MAX_DISTANCE_M
    }

    private fun isMotorway(zone: Zone): Boolean {
        return zone.road.startsWith("АМ ") || zone.road.startsWith("AM ")
    }
}
