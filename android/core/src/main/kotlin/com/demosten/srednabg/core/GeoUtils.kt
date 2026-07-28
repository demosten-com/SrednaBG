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

// The projection of a point onto one polyline segment: the clamped parameter
// [t] in [0, 1], the projected lat/lng, and the haversine distance from the
// point to that projection. Shared by the three callers below so the flat-earth
// projection math lives in exactly one place.
private data class SegmentProjection(
    val t: Double,
    val projLat: Double,
    val projLng: Double,
    val distanceM: Double,
)

// Flat-earth projection of P onto segment A→B with cos(lat) correction for
// longitude, clamped to the segment. A degenerate segment (A == B) yields t = 0,
// i.e. the projection collapses to A — so the returned distance is haversine(P, A).
private fun projectPointOntoSegment(
    pLat: Double, pLng: Double,
    aLat: Double, aLng: Double,
    bLat: Double, bLng: Double,
): SegmentProjection {
    val midLat = Math.toRadians((aLat + bLat) / 2)
    val cosLat = cos(midLat)
    val metersPerDegLat = 111_320.0
    val metersPerDegLng = 111_320.0 * cosLat

    val bx = (bLng - aLng) * metersPerDegLng
    val by = (bLat - aLat) * metersPerDegLat
    val px = (pLng - aLng) * metersPerDegLng
    val py = (pLat - aLat) * metersPerDegLat

    val abLenSq = bx * bx + by * by
    val t = if (abLenSq < 1e-10) 0.0 else ((px * bx + py * by) / abLenSq).coerceIn(0.0, 1.0)

    val projLat = aLat + t * (bLat - aLat)
    val projLng = aLng + t * (bLng - aLng)
    return SegmentProjection(t, projLat, projLng, haversineDistance(pLat, pLng, projLat, projLng))
}

fun pointToSegmentDistance(
    pLat: Double, pLng: Double,
    aLat: Double, aLng: Double,
    bLat: Double, bLng: Double,
): Double {
    return projectPointOntoSegment(pLat, pLng, aLat, aLng, bLat, bLng).distanceM
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
        val proj = projectPointOntoSegment(
            lat, lng,
            polyline[i][0], polyline[i][1],
            polyline[i + 1][0], polyline[i + 1][1],
        )

        if (proj.distanceM < bestDist) {
            bestDist = proj.distanceM
            bestLat = proj.projLat
            bestLng = proj.projLng
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

/**
 * Where a point sits relative to a polyline: how far along it the projection
 * falls ([arcLengthM]) and how far off the line the point is
 * ([distanceFromLineM]).
 *
 * Both numbers come out of the same walk of the segments. The zone hot path
 * needs both for every candidate zone on every fix (the on-road band test, the
 * nearest-zone tie-break, the local-heading test, and the remaining distance),
 * and computing them separately walked all 72 centerlines three times per fix.
 */
data class PolylinePosition(
    val arcLengthM: Double,
    val distanceFromLineM: Double,
)

/**
 * Project (lat, lng) onto [polyline] and report both the arc length to the
 * projection and the offset from the line. Null when the polyline has no
 * segment to project onto.
 */
fun positionOnPolyline(lat: Double, lng: Double, polyline: List<List<Double>>): PolylinePosition? {
    if (polyline.size < 2) return null

    var bestDist = Double.MAX_VALUE
    var bestCumulative = 0.0
    var cumulative = 0.0

    for (i in 0 until polyline.size - 1) {
        val aLat = polyline[i][0]
        val aLng = polyline[i][1]
        val bLat = polyline[i + 1][0]
        val bLng = polyline[i + 1][1]

        val segLen = haversineDistance(aLat, aLng, bLat, bLng)
        val proj = projectPointOntoSegment(lat, lng, aLat, aLng, bLat, bLng)

        if (proj.distanceM < bestDist) {
            bestDist = proj.distanceM
            bestCumulative = cumulative + proj.t * segLen
        }

        cumulative += segLen
    }
    return PolylinePosition(bestCumulative, bestDist)
}

/**
 * Arc length (metres) from the polyline start to the projection of (lat, lng)
 * onto the polyline — i.e. how far along the line the point sits. Returns a
 * scalar; contrast [projectPointOntoPolyline], which returns the projected
 * point's coordinates/bearing/offset as a [PolylineProjection].
 */
fun arcLengthOnPolyline(lat: Double, lng: Double, polyline: List<List<Double>>): Double =
    positionOnPolyline(lat, lng, polyline)?.arcLengthM ?: 0.0

/** The point sitting [arcLengthM] along [polyline], clamped to its two ends. */
fun pointAtArcLength(polyline: List<List<Double>>, arcLengthM: Double): List<Double> {
    if (polyline.isEmpty()) return emptyList()
    if (polyline.size == 1 || arcLengthM <= 0.0) return polyline.first()

    var remaining = arcLengthM
    for (i in 0 until polyline.size - 1) {
        val segLen = haversineDistance(
            polyline[i][0], polyline[i][1],
            polyline[i + 1][0], polyline[i + 1][1],
        )
        if (remaining <= segLen) {
            val t = if (segLen <= 0.0) 0.0 else remaining / segLen
            return listOf(
                polyline[i][0] + t * (polyline[i + 1][0] - polyline[i][0]),
                polyline[i][1] + t * (polyline[i + 1][1] - polyline[i][1]),
            )
        }
        remaining -= segLen
    }
    return polyline.last()
}

/**
 * The polyline's heading *in the neighbourhood of* [arcLengthM] — the bearing
 * from the point [windowM] back along the line to the point [windowM] ahead of
 * it, clamped at the ends.
 *
 * Contrast [polylineBearing], which is the single first→last bearing of the
 * whole line. On a 10–25 km zone that whole-line bearing says almost nothing
 * about which way the road actually runs at a given place: it let a fix whose
 * course was 45° off the *local* road pass the direction test purely because it
 * happened to align with the zone end-to-end (see [PolylinePosition] callers in
 * RoadMatcher).
 *
 * Reading it over a window rather than off the nearest single segment also makes
 * it immune to short backwards jogs in the stored geometry — 31 of the 72 zones
 * have a first segment pointing >90° away from the zone's overall direction
 * (jogs of 6–122 m), which a bare nearest-segment bearing would read as "driving
 * the wrong way" and reject at the zone start.
 */
fun localPolylineBearing(
    polyline: List<List<Double>>,
    arcLengthM: Double,
    windowM: Double,
): Double? {
    if (polyline.size < 2) return null
    val total = polylineLengthMeters(polyline)
    if (total <= 0.0) return null

    // Keep the window a full 2 * windowM wide wherever the line is long enough,
    // sliding it inward at the ends rather than letting it collapse (a bearing
    // read across a few metres at the very start is pure vertex noise).
    val span = minOf(2 * windowM, total)
    val from = (arcLengthM - windowM).coerceIn(0.0, total - span)
    val to = from + span

    // pointAtArcLength returns an empty list only for an empty polyline, which
    // the size guard above already rules out — but it is the caller's job to say
    // so, not to index into whatever comes back.
    val a = pointAtArcLength(polyline, from).takeIf { it.size >= 2 } ?: return null
    val b = pointAtArcLength(polyline, to).takeIf { it.size >= 2 } ?: return null
    return bearingBetween(a[0], a[1], b[0], b[1])
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
