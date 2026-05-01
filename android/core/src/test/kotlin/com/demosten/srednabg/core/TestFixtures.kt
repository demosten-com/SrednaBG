// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

const val EPOCH_BASE = 1_700_000_000_000L

// Trakiya t10: Ihtiman -> Vakarel (west direction), 19160m, 140 km/h
val TRAKIYA_T10 = Zone(
    id = "trakiya-01-west",
    road = "АМ Тракия",
    roadLatin = "Trakiya",
    direction = "west",
    description = "Ихтиман – Вакарел",
    start = ZoneEndpoint(lat = 42.427, lng = 23.855, settlement = "Ихтиман"),
    end = ZoneEndpoint(lat = 42.550, lng = 23.703, settlement = "Вакарел"),
    distanceM = 19160,
    speedLimits = SpeedLimits(car = 140, truck = 90, bus = 100, motorcycle = 140),
    centerline = listOf(
        listOf(42.427, 23.855),
        listOf(42.450, 23.830),
        listOf(42.480, 23.800),
        listOf(42.510, 23.770),
        listOf(42.530, 23.740),
        listOf(42.550, 23.703),
    ),
    source = "tolltracker",
    lastVerified = "2026-04-12",
)

// Hemus h12: Gorni Bogrov -> Churek (east direction), 20200m, 140 km/h
val HEMUS_H12 = Zone(
    id = "hemus-01-east",
    road = "АМ Хемус",
    roadLatin = "Hemus",
    direction = "east",
    description = "Горни Богров – Чурек",
    start = ZoneEndpoint(lat = 42.725, lng = 23.528, settlement = "Горни Богров"),
    end = ZoneEndpoint(lat = 42.779, lng = 23.736, settlement = "Чурек"),
    distanceM = 20200,
    speedLimits = SpeedLimits(car = 140, truck = 90, bus = 100, motorcycle = 140),
    centerline = listOf(
        listOf(42.725, 23.528),
        listOf(42.740, 23.580),
        listOf(42.755, 23.640),
        listOf(42.770, 23.700),
        listOf(42.779, 23.736),
    ),
    source = "tolltracker",
    lastVerified = "2026-04-12",
)

// I-4 i4-10: Sopot -> Balgarski Izvor (east direction), 9200m, 90 km/h
val I4_10 = Zone(
    id = "i4-01-east",
    road = "Път I-4",
    roadLatin = "I-4",
    direction = "east",
    description = "Сопот – Български Извор",
    start = ZoneEndpoint(lat = 43.269, lng = 24.949, settlement = "Сопот"),
    end = ZoneEndpoint(lat = 43.308, lng = 25.075, settlement = "Български Извор"),
    distanceM = 9200,
    speedLimits = SpeedLimits(car = 90, truck = 80, bus = 80, motorcycle = 90),
    centerline = listOf(
        listOf(43.269, 24.949),
        listOf(43.280, 24.980),
        listOf(43.292, 25.020),
        listOf(43.300, 25.050),
        listOf(43.308, 25.075),
    ),
    source = "tolltracker",
    lastVerified = "2026-04-12",
)

/**
 * Generate a GPS trace along a zone's centerline at constant speed.
 * Includes approach points before the zone start and departure points after the zone end.
 */
fun generateGpsTrace(
    zone: Zone,
    speedKmh: Double,
    intervalMs: Long = 1000L,
    startTime: Long = EPOCH_BASE,
): List<GpsPoint> {
    val points = mutableListOf<GpsPoint>()
    val centerline = zone.centerline
    if (centerline.size < 2) return points

    // Compute total polyline length and segment lengths
    val segLengths = mutableListOf<Double>()
    var totalLength = 0.0
    for (i in 0 until centerline.size - 1) {
        val len = haversineDistance(
            centerline[i][0], centerline[i][1],
            centerline[i + 1][0], centerline[i + 1][1],
        )
        segLengths.add(len)
        totalLength += len
    }

    val speedMs = speedKmh / 3.6
    val distPerTick = speedMs * (intervalMs / 1000.0)

    // Generate approach points (3 points before zone start, ~200m before)
    val approachBearing = bearingBetween(
        centerline[1][0], centerline[1][1],
        centerline[0][0], centerline[0][1],
    )
    for (i in 3 downTo 1) {
        val offsetM = i * 200.0
        val offsetDegLat = (offsetM * kotlin.math.cos(Math.toRadians(approachBearing))) / 111_320.0
        val offsetDegLng = (offsetM * kotlin.math.sin(Math.toRadians(approachBearing))) /
            (111_320.0 * kotlin.math.cos(Math.toRadians(centerline[0][0])))
        val bearing = bearingBetween(
            centerline[0][0] + offsetDegLat, centerline[0][1] + offsetDegLng,
            centerline[0][0], centerline[0][1],
        )
        points.add(
            GpsPoint(
                lat = centerline[0][0] + offsetDegLat,
                lng = centerline[0][1] + offsetDegLng,
                speed = speedKmh,
                timestamp = startTime - i * intervalMs,
                bearing = bearing,
            ),
        )
    }

    // Generate points along the centerline
    var currentDist = 0.0
    var segIdx = 0
    var segStart = 0.0
    var time = startTime

    while (currentDist <= totalLength && segIdx < segLengths.size) {
        val distInSeg = currentDist - segStart
        val t = if (segLengths[segIdx] > 0) distInSeg / segLengths[segIdx] else 0.0

        val lat = centerline[segIdx][0] + t * (centerline[segIdx + 1][0] - centerline[segIdx][0])
        val lng = centerline[segIdx][1] + t * (centerline[segIdx + 1][1] - centerline[segIdx][1])
        val bearing = bearingBetween(
            centerline[segIdx][0], centerline[segIdx][1],
            centerline[segIdx + 1][0], centerline[segIdx + 1][1],
        )

        points.add(GpsPoint(lat = lat, lng = lng, speed = speedKmh, timestamp = time, bearing = bearing))

        currentDist += distPerTick
        time += intervalMs

        // Advance to next segment if needed
        while (segIdx < segLengths.size && currentDist - segStart > segLengths[segIdx]) {
            segStart += segLengths[segIdx]
            segIdx++
        }
    }

    // Generate departure points (3 points after zone end)
    val lastCl = centerline.last()
    val prevCl = centerline[centerline.size - 2]
    val exitBearing = bearingBetween(prevCl[0], prevCl[1], lastCl[0], lastCl[1])
    for (i in 1..3) {
        time += intervalMs
        val offsetM = i * distPerTick
        val offsetDegLat = (offsetM * kotlin.math.cos(Math.toRadians(exitBearing))) / 111_320.0
        val offsetDegLng = (offsetM * kotlin.math.sin(Math.toRadians(exitBearing))) /
            (111_320.0 * kotlin.math.cos(Math.toRadians(lastCl[0])))
        points.add(
            GpsPoint(
                lat = lastCl[0] + offsetDegLat,
                lng = lastCl[1] + offsetDegLng,
                speed = speedKmh,
                timestamp = time,
                bearing = exitBearing,
            ),
        )
    }

    return points
}

/**
 * Generate a GPS trace with a stop at the given fraction through the zone.
 */
fun generateTraceWithStop(
    zone: Zone,
    speedKmh: Double,
    stopAtFraction: Double = 0.5,
    stopDurationMs: Long = 120_000L,
    intervalMs: Long = 1000L,
    startTime: Long = EPOCH_BASE,
): List<GpsPoint> {
    val fullTrace = generateGpsTrace(zone, speedKmh, intervalMs, startTime)

    // Find the point closest to the stop fraction
    val approachCount = 3 // approach points before zone
    val zonePoints = fullTrace.drop(approachCount).dropLast(3)
    val stopIdx = approachCount + (zonePoints.size * stopAtFraction).toInt()

    if (stopIdx >= fullTrace.size) return fullTrace

    val stopPoint = fullTrace[stopIdx]
    val result = mutableListOf<GpsPoint>()

    // Add points before stop
    result.addAll(fullTrace.subList(0, stopIdx))

    // Add stop points
    val numStopPoints = (stopDurationMs / intervalMs).toInt()
    for (i in 0 until numStopPoints) {
        result.add(
            GpsPoint(
                lat = stopPoint.lat,
                lng = stopPoint.lng,
                speed = 0.0,
                timestamp = stopPoint.timestamp + i * intervalMs,
                bearing = stopPoint.bearing,
            ),
        )
    }

    // Add remaining points with shifted timestamps
    val timeShift = stopDurationMs
    for (i in stopIdx until fullTrace.size) {
        result.add(fullTrace[i].copy(timestamp = fullTrace[i].timestamp + timeShift))
    }

    return result
}

// Overlapping zone: same road as Trakiya T10 but opposite direction (east)
val TRAKIYA_T10_OPPOSITE = Zone(
    id = "trakiya-01-east",
    road = "АМ Тракия",
    roadLatin = "Trakiya",
    direction = "east",
    description = "Вакарел – Ихтиман",
    start = ZoneEndpoint(lat = 42.550, lng = 23.703, settlement = "Вакарел"),
    end = ZoneEndpoint(lat = 42.427, lng = 23.855, settlement = "Ихтиман"),
    distanceM = 19160,
    speedLimits = SpeedLimits(car = 140, truck = 90, bus = 100, motorcycle = 140),
    centerline = listOf(
        listOf(42.550, 23.703),
        listOf(42.530, 23.740),
        listOf(42.510, 23.770),
        listOf(42.480, 23.800),
        listOf(42.450, 23.830),
        listOf(42.427, 23.855),
    ),
    source = "tolltracker",
    lastVerified = "2026-04-12",
)

// National road zone (not motorway, so standard 100m threshold applies)
val NATIONAL_ROAD_ZONE = Zone(
    id = "i1-01-east",
    road = "Път I-1",
    roadLatin = "I-1",
    direction = "east",
    description = "Test national road",
    start = ZoneEndpoint(lat = 42.700, lng = 23.400),
    end = ZoneEndpoint(lat = 42.710, lng = 23.500),
    distanceM = 8000,
    speedLimits = SpeedLimits(car = 90, truck = 80, bus = 80),
    centerline = listOf(
        listOf(42.700, 23.400),
        listOf(42.705, 23.450),
        listOf(42.710, 23.500),
    ),
    source = "test",
    lastVerified = "2026-04-12",
)

/**
 * Generate a GPS trace that exits the zone at a given fraction, goes off-road
 * for a given duration, then re-enters the same zone.
 */
fun generateReentryTrace(
    zone: Zone,
    speedKmh: Double,
    exitAtFraction: Double = 0.3,
    offRoadDurationMs: Long = 120_000L,
    intervalMs: Long = 1000L,
    startTime: Long = EPOCH_BASE,
): List<GpsPoint> {
    val fullTrace = generateGpsTrace(zone, speedKmh, intervalMs, startTime)
    val approachCount = 3
    val zonePoints = fullTrace.drop(approachCount).dropLast(3)
    val exitIdx = approachCount + (zonePoints.size * exitAtFraction).toInt()

    if (exitIdx >= fullTrace.size - 10) return fullTrace

    val result = mutableListOf<GpsPoint>()
    // Points before exit
    result.addAll(fullTrace.subList(0, exitIdx))

    // Off-road points: move perpendicular to centerline (200m away, beyond threshold)
    val exitPoint = fullTrace[exitIdx]
    val offRoadCount = (offRoadDurationMs / intervalMs).toInt()
    val offsetLat = 0.003 // ~330m offset perpendicular
    for (i in 0 until offRoadCount) {
        result.add(
            GpsPoint(
                lat = exitPoint.lat + offsetLat,
                lng = exitPoint.lng,
                speed = 5.0, // slow movement
                timestamp = exitPoint.timestamp + i * intervalMs,
                bearing = exitPoint.bearing,
            ),
        )
    }

    // Re-entry: return to road and continue from same position
    val reentryTime = exitPoint.timestamp + offRoadDurationMs
    val remainingPoints = fullTrace.subList(exitIdx, fullTrace.size)
    val timeShift = reentryTime - exitPoint.timestamp
    for (point in remainingPoints) {
        result.add(point.copy(timestamp = point.timestamp + timeShift))
    }

    return result
}

/**
 * Add random noise to a GPS trace to simulate GPS inaccuracy.
 */
fun addNoiseToTrace(
    trace: List<GpsPoint>,
    noiseMeters: Double = 5.0,
    random: java.util.Random = java.util.Random(42),
): List<GpsPoint> {
    return trace.map { point ->
        val noiseLat = (random.nextGaussian() * noiseMeters) / 111_320.0
        val noiseLng = (random.nextGaussian() * noiseMeters) /
            (111_320.0 * kotlin.math.cos(Math.toRadians(point.lat)))
        point.copy(
            lat = point.lat + noiseLat,
            lng = point.lng + noiseLng,
            accuracy = noiseMeters * 2,
        )
    }
}

/**
 * Generate a GPS trace with a GPS dropout (gap in timestamps) at the given fraction.
 */
fun generateTraceWithDropout(
    zone: Zone,
    speedKmh: Double,
    dropoutAtFraction: Double = 0.5,
    dropoutDurationMs: Long = 15_000L,
    intervalMs: Long = 1000L,
    startTime: Long = EPOCH_BASE,
): List<GpsPoint> {
    val fullTrace = generateGpsTrace(zone, speedKmh, intervalMs, startTime)

    val approachCount = 3
    val zonePoints = fullTrace.drop(approachCount).dropLast(3)
    val dropoutIdx = approachCount + (zonePoints.size * dropoutAtFraction).toInt()

    if (dropoutIdx >= fullTrace.size - 1) return fullTrace

    val result = mutableListOf<GpsPoint>()

    // Add points before dropout
    result.addAll(fullTrace.subList(0, dropoutIdx))

    // Skip points during the dropout, shift timestamps after
    val timeShift = dropoutDurationMs - intervalMs // extra time beyond normal interval
    for (i in dropoutIdx until fullTrace.size) {
        result.add(fullTrace[i].copy(timestamp = fullTrace[i].timestamp + timeShift))
    }

    return result
}
