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

/**
 * A straight motorway zone whose centerline is densely sampled with segments far
 * shorter than the per-second travel distance — the real-world shape (e.g.
 * struma-02-south: 71 of 101 segments under 30 m) that exposed the speed×time
 * integrator drift. Built programmatically so the segment count is obvious.
 */
fun denseShortSegmentZone(
    distanceM: Int = 2300,
    segmentM: Double = 15.0,
    speedLimitCar: Int = 140,
): Zone {
    val startLat = 42.0
    val startLng = 23.0
    val degPerMeterLat = 1.0 / 111_320.0
    val n = (distanceM / segmentM).toInt()
    val centerline = (0..n).map { i ->
        listOf(startLat + i * segmentM * degPerMeterLat, startLng)
    }
    return Zone(
        id = "dense-01-north",
        road = "АМ Тест",
        roadLatin = "Test",
        direction = "north",
        description = "Dense centerline",
        start = ZoneEndpoint(lat = centerline.first()[0], lng = startLng),
        end = ZoneEndpoint(lat = centerline.last()[0], lng = startLng),
        distanceM = distanceM,
        speedLimits = SpeedLimits(car = speedLimitCar, truck = 90, bus = 100, motorcycle = speedLimitCar),
        centerline = centerline,
        source = "test",
        lastVerified = "2026-04-12",
    )
}

/**
 * Walk a zone's centerline emitting one fix per vertex at a fixed time interval,
 * tagging every fix with a constant [reportedSpeedKmh] regardless of the (uneven)
 * geographic spacing. This mirrors `qa/feed_zone.py`'s pre-fix behavior: short
 * centerline segments produced sub-`reportedSpeed×interval` hops while the feed
 * advertised a constant cruise speed, so the app's speed×time integrator
 * over-counted distance. Use it to assert the detector no longer mistakes that
 * drift for an early zone exit. Includes 4 approach fixes before the start.
 */
/**
 * The shared physical centerline of the europa-01 pair (Iliyantsi ⇄ Chepintsi on
 * АМ Европа), running start → end (south endpoint → north endpoint, i.e. the
 * northbound carriageway's true direction). ~9.9 km.
 */
val EUROPA_PHYSICAL_CENTERLINE: List<List<Double>> = listOf(
    listOf(42.7197, 23.4005),
    listOf(42.73115, 23.374875),
    listOf(42.7426, 23.34925),
    listOf(42.75405, 23.323625),
    listOf(42.765501, 23.297023),
)

/**
 * The europa-01 sibling pair as the **server actually serves it**: two
 * opposite-carriageway zones sharing the same physical centerline geometry, where
 * the NORTH zone's centerline is stored **end-first** (the real data bug observed
 * live via `qa/feed-zone.sh 0`). Its raw first→last bearing then points the way
 * the SOUTH sibling travels, so any direction matching that keys off raw point
 * order matches `europa-test-south` for a northbound drive. Both zones carry
 * correct start/end endpoints, which is what lets the engine recover by orienting
 * to them ([orientCenterlineToStart]).
 *
 * [first] is north (centerline reversed), [second] is south.
 */
fun europaReversedSiblings(): Pair<Zone, Zone> {
    val a = EUROPA_PHYSICAL_CENTERLINE.first()
    val b = EUROPA_PHYSICAL_CENTERLINE.last()
    val north = Zone(
        id = "europa-test-north",
        road = "АМ Европа",
        roadLatin = "Evropa",
        direction = "north",
        description = "Илиянци – Чепинци (northbound, centerline stored end-first)",
        start = ZoneEndpoint(lat = a[0], lng = a[1], settlement = "Илиянци"),
        end = ZoneEndpoint(lat = b[0], lng = b[1], settlement = "Чепинци"),
        distanceM = 9874,
        speedLimits = SpeedLimits(car = 120, truck = 90, bus = 100, motorcycle = 120),
        // The bug: points stored end → start.
        centerline = EUROPA_PHYSICAL_CENTERLINE.reversed(),
        source = "bgtoll",
        lastVerified = "2026-04-12",
    )
    val south = Zone(
        id = "europa-test-south",
        road = "АМ Европа",
        roadLatin = "Evropa",
        direction = "south",
        description = "Чепинци – Илиянци (southbound)",
        start = ZoneEndpoint(lat = b[0], lng = b[1], settlement = "Чепинци"),
        end = ZoneEndpoint(lat = a[0], lng = a[1], settlement = "Илиянци"),
        distanceM = 9874,
        speedLimits = SpeedLimits(car = 120, truck = 90, bus = 100, motorcycle = 120),
        // Stored start→end for *its* endpoints = a→b physical order, i.e. the same
        // direction the northbound drive heads — so a point-order bearing match
        // wrongly admits this sibling.
        centerline = EUROPA_PHYSICAL_CENTERLINE,
        source = "bgtoll",
        lastVerified = "2026-04-12",
    )
    return north to south
}

/**
 * A northbound GPS trace along [EUROPA_PHYSICAL_CENTERLINE] (start → end, the true
 * physical direction), independent of how any zone stored its centerline. Used to
 * drive [europaReversedSiblings] the way `qa/feed-zone.sh` does (oriented by the
 * endpoints).
 */
fun europaNorthboundTrace(speedKmh: Double = 108.0): List<GpsPoint> {
    val carrier = Zone(
        id = "europa-trace-carrier",
        road = "АМ Европа",
        roadLatin = "Evropa",
        direction = "north",
        description = "trace carrier",
        start = ZoneEndpoint(lat = EUROPA_PHYSICAL_CENTERLINE.first()[0], lng = EUROPA_PHYSICAL_CENTERLINE.first()[1]),
        end = ZoneEndpoint(lat = EUROPA_PHYSICAL_CENTERLINE.last()[0], lng = EUROPA_PHYSICAL_CENTERLINE.last()[1]),
        distanceM = 9874,
        speedLimits = SpeedLimits(car = 120, truck = 90, bus = 100, motorcycle = 120),
        centerline = EUROPA_PHYSICAL_CENTERLINE,
        source = "test",
        lastVerified = "2026-04-12",
    )
    return generateGpsTrace(carrier, speedKmh)
}

fun generateUnevenSpacingTrace(
    zone: Zone,
    reportedSpeedKmh: Double,
    intervalMs: Long = 1000L,
    startTime: Long = EPOCH_BASE,
): List<GpsPoint> {
    val cl = zone.centerline
    val bearing = polylineBearing(cl)
    val points = mutableListOf<GpsPoint>()

    // Approach fixes ~one segment apart behind the start, heading into the zone.
    val approachBearing = (bearing + 180) % 360
    val segM = haversineDistance(cl[0][0], cl[0][1], cl[1][0], cl[1][1])
    for (k in 4 downTo 1) {
        val offsetM = k * segM
        val lat = cl[0][0] + (offsetM * kotlin.math.cos(Math.toRadians(approachBearing))) / 111_320.0
        points.add(
            GpsPoint(
                lat = lat, lng = cl[0][1], speed = reportedSpeedKmh,
                timestamp = startTime - k * intervalMs, bearing = bearing,
            ),
        )
    }
    for ((i, v) in cl.withIndex()) {
        points.add(
            GpsPoint(
                lat = v[0], lng = v[1], speed = reportedSpeedKmh,
                timestamp = startTime + i * intervalMs, bearing = bearing,
            ),
        )
    }
    return points
}
