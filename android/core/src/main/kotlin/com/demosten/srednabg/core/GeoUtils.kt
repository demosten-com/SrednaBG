// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

private const val EARTH_RADIUS_M = 6_371_000.0

fun haversineDistance(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
    val lat1R = Math.toRadians(lat1)
    val lat2R = Math.toRadians(lat2)
    val dLat = Math.toRadians(lat2 - lat1)
    val dLng = Math.toRadians(lng2 - lng1)
    val a = sin(dLat / 2) * sin(dLat / 2) +
        cos(lat1R) * cos(lat2R) * sin(dLng / 2) * sin(dLng / 2)
    return EARTH_RADIUS_M * 2 * atan2(sqrt(a), sqrt(1 - a))
}

fun pointToSegmentDistance(
    pLat: Double, pLng: Double,
    aLat: Double, aLng: Double,
    bLat: Double, bLng: Double,
): Double {
    // Flat-earth projection with cos(lat) correction for longitude
    val midLat = Math.toRadians((aLat + bLat) / 2)
    val cosLat = cos(midLat)
    val metersPerDegLat = 111_320.0
    val metersPerDegLng = 111_320.0 * cosLat

    val bx = (bLng - aLng) * metersPerDegLng
    val by = (bLat - aLat) * metersPerDegLat
    val px = (pLng - aLng) * metersPerDegLng
    val py = (pLat - aLat) * metersPerDegLat

    val abLenSq = bx * bx + by * by
    if (abLenSq < 1e-10) {
        // Degenerate segment (A == B)
        return haversineDistance(pLat, pLng, aLat, aLng)
    }

    // Project P onto line A-B, clamped to [0, 1]
    val t = ((px * bx + py * by) / abLenSq).coerceIn(0.0, 1.0)
    val projLng = aLng + t * (bLng - aLng)
    val projLat = aLat + t * (bLat - aLat)

    return haversineDistance(pLat, pLng, projLat, projLng)
}

fun pointToPolylineDistance(lat: Double, lng: Double, polyline: List<List<Double>>): Double {
    if (polyline.isEmpty()) return Double.MAX_VALUE
    if (polyline.size == 1) return haversineDistance(lat, lng, polyline[0][0], polyline[0][1])

    var minDist = Double.MAX_VALUE
    for (i in 0 until polyline.size - 1) {
        val d = pointToSegmentDistance(
            lat, lng,
            polyline[i][0], polyline[i][1],
            polyline[i + 1][0], polyline[i + 1][1],
        )
        if (d < minDist) minDist = d
    }
    return minDist
}

fun snapToZone(pos: GpsPoint?, state: ZoneState): GpsPoint? {
    if (pos == null) return null
    if (state !is ZoneState.InZone) return pos
    val proj = projectPointOntoPolyline(pos.lat, pos.lng, state.zone.centerline) ?: return pos
    return pos.copy(lat = proj.lat, lng = proj.lng, bearing = proj.bearing)
}

data class PolylineProjection(
    val lat: Double,
    val lng: Double,
    val bearing: Double,
    val distanceFromLineM: Double,
)

fun projectPointOntoPolyline(
    lat: Double,
    lng: Double,
    polyline: List<List<Double>>,
): PolylineProjection? {
    if (polyline.size < 2) return null

    var bestDist = Double.MAX_VALUE
    var bestLat = 0.0
    var bestLng = 0.0
    var bestSegA: List<Double> = polyline[0]
    var bestSegB: List<Double> = polyline[1]

    for (i in 0 until polyline.size - 1) {
        val aLat = polyline[i][0]
        val aLng = polyline[i][1]
        val bLat = polyline[i + 1][0]
        val bLng = polyline[i + 1][1]

        val midLat = Math.toRadians((aLat + bLat) / 2)
        val cosLat = cos(midLat)
        val mLat = 111_320.0
        val mLng = 111_320.0 * cosLat

        val bx = (bLng - aLng) * mLng
        val by = (bLat - aLat) * mLat
        val px = (lng - aLng) * mLng
        val py = (lat - aLat) * mLat

        val abLenSq = bx * bx + by * by
        val t = if (abLenSq < 1e-10) 0.0 else ((px * bx + py * by) / abLenSq).coerceIn(0.0, 1.0)

        val projLat = aLat + t * (bLat - aLat)
        val projLng = aLng + t * (bLng - aLng)
        val d = haversineDistance(lat, lng, projLat, projLng)

        if (d < bestDist) {
            bestDist = d
            bestLat = projLat
            bestLng = projLng
            bestSegA = polyline[i]
            bestSegB = polyline[i + 1]
        }
    }

    val bearing = bearingBetween(bestSegA[0], bestSegA[1], bestSegB[0], bestSegB[1])
    return PolylineProjection(bestLat, bestLng, bearing, bestDist)
}

/** Total arc length (metres) of a [[lat, lng], ...] polyline. */
fun polylineLengthMeters(polyline: List<List<Double>>): Double {
    if (polyline.size < 2) return 0.0
    var total = 0.0
    for (i in 0 until polyline.size - 1) {
        total += haversineDistance(
            polyline[i][0], polyline[i][1],
            polyline[i + 1][0], polyline[i + 1][1],
        )
    }
    return total
}

fun projectOntoPolyline(lat: Double, lng: Double, polyline: List<List<Double>>): Double {
    if (polyline.size < 2) return 0.0

    var bestDist = Double.MAX_VALUE
    var bestCumulative = 0.0
    var cumulative = 0.0

    for (i in 0 until polyline.size - 1) {
        val aLat = polyline[i][0]
        val aLng = polyline[i][1]
        val bLat = polyline[i + 1][0]
        val bLng = polyline[i + 1][1]

        val segLen = haversineDistance(aLat, aLng, bLat, bLng)

        // Compute projection parameter t
        val midLat = Math.toRadians((aLat + bLat) / 2)
        val cosLat = cos(midLat)
        val mLat = 111_320.0
        val mLng = 111_320.0 * cosLat

        val bx = (bLng - aLng) * mLng
        val by = (bLat - aLat) * mLat
        val px = (lng - aLng) * mLng
        val py = (lat - aLat) * mLat

        val abLenSq = bx * bx + by * by
        val t = if (abLenSq < 1e-10) 0.0 else ((px * bx + py * by) / abLenSq).coerceIn(0.0, 1.0)

        val projLat = aLat + t * (bLat - aLat)
        val projLng = aLng + t * (bLng - aLng)
        val d = haversineDistance(lat, lng, projLat, projLng)

        if (d < bestDist) {
            bestDist = d
            bestCumulative = cumulative + t * segLen
        }

        cumulative += segLen
    }
    return bestCumulative
}

fun bearingBetween(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
    val lat1R = Math.toRadians(lat1)
    val lat2R = Math.toRadians(lat2)
    val dLng = Math.toRadians(lng2 - lng1)
    val x = sin(dLng) * cos(lat2R)
    val y = cos(lat1R) * sin(lat2R) - sin(lat1R) * cos(lat2R) * cos(dLng)
    val bearing = Math.toDegrees(atan2(x, y))
    return (bearing + 360) % 360
}

fun bearingDifference(b1: Double, b2: Double): Double {
    val diff = abs(b1 - b2) % 360
    return if (diff > 180) 360 - diff else diff
}

// Null on an unknown direction string so bad server data degrades to
// "no match" instead of crashing — mirrors the Swift port.
fun directionToBearing(direction: String): Double? = when (direction) {
    "north" -> 0.0
    "east" -> 90.0
    "south" -> 180.0
    "west" -> 270.0
    else -> null
}

fun polylineBearing(polyline: List<List<Double>>): Double {
    if (polyline.size < 2) throw IllegalArgumentException("Polyline must have at least 2 points")
    val first = polyline.first()
    val last = polyline.last()
    return bearingBetween(first[0], first[1], last[0], last[1])
}

/**
 * Return [centerline] guaranteed to run from [start] toward the far endpoint,
 * reversing it when it was stored end-first.
 *
 * Direction matching ([polylineBearing]), polyline projection, and the remaining
 * distance all key off the centerline's point order. A centerline stored
 * end-first — a real server-data bug (see qa/feed-zone.sh / qa/validate-zones.sh;
 * the scraper's `align_centerline_to_endpoints` fixes the bundle, but the live
 * `/api/zones` may still serve it and the device syncs that into Room) — flips a
 * zone's apparent first→last bearing 180°, so the app matches the
 * opposite-carriageway sibling and reports an inverted "remaining". Each zone's
 * start/end endpoints are authoritative, so orienting against [start] here makes
 * the whole engine immune to the bad point order regardless of where the data
 * came from.
 */
fun orientCenterlineToStart(
    centerline: List<List<Double>>,
    start: ZoneEndpoint,
): List<List<Double>> {
    if (centerline.size < 2) return centerline
    val first = centerline.first()
    val last = centerline.last()
    val firstToStart = haversineDistance(first[0], first[1], start.lat, start.lng)
    val lastToStart = haversineDistance(last[0], last[1], start.lat, start.lng)
    return if (firstToStart <= lastToStart) centerline else centerline.reversed()
}
