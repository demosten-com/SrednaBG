// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

// Fixture constants deliberately mirror the names of their Kotlin
// counterparts (`TRAKIYA_T10`, `HEMUS_H12`, …) so cross-language diffing
// is easy. Allow UPPER_SNAKE_CASE here only.
// swiftlint:disable identifier_name
import Foundation
@testable import SrednaBGCore

let epochBase: Int64 = 1_700_000_000_000

// Trakiya t10: Ihtiman -> Vakarel (west direction), 19160m, 140 km/h
let TRAKIYA_T10 = Zone(
    id: "trakiya-01-west",
    road: "АМ Тракия",
    roadLatin: "Trakiya",
    direction: "west",
    description: "Ихтиман – Вакарел",
    start: ZoneEndpoint(lat: 42.427, lng: 23.855, settlement: "Ихтиман"),
    end: ZoneEndpoint(lat: 42.550, lng: 23.703, settlement: "Вакарел"),
    distanceM: 19160,
    speedLimits: SpeedLimits(car: 140, truck: 90, bus: 100, motorcycle: 140),
    centerline: [
        [42.427, 23.855],
        [42.450, 23.830],
        [42.480, 23.800],
        [42.510, 23.770],
        [42.530, 23.740],
        [42.550, 23.703]
    ],
    source: "tolltracker",
    lastVerified: "2026-04-12"
)

// Hemus h12: Gorni Bogrov -> Churek (east direction), 20200m, 140 km/h
let HEMUS_H12 = Zone(
    id: "hemus-01-east",
    road: "АМ Хемус",
    roadLatin: "Hemus",
    direction: "east",
    description: "Горни Богров – Чурек",
    start: ZoneEndpoint(lat: 42.725, lng: 23.528, settlement: "Горни Богров"),
    end: ZoneEndpoint(lat: 42.779, lng: 23.736, settlement: "Чурек"),
    distanceM: 20200,
    speedLimits: SpeedLimits(car: 140, truck: 90, bus: 100, motorcycle: 140),
    centerline: [
        [42.725, 23.528],
        [42.740, 23.580],
        [42.755, 23.640],
        [42.770, 23.700],
        [42.779, 23.736]
    ],
    source: "tolltracker",
    lastVerified: "2026-04-12"
)

// I-4 i4-10: Sopot -> Balgarski Izvor (east direction), 9200m, 90 km/h
let I4_10 = Zone(
    id: "i4-01-east",
    road: "Път I-4",
    roadLatin: "I-4",
    direction: "east",
    description: "Сопот – Български Извор",
    start: ZoneEndpoint(lat: 43.269, lng: 24.949, settlement: "Сопот"),
    end: ZoneEndpoint(lat: 43.308, lng: 25.075, settlement: "Български Извор"),
    distanceM: 9200,
    speedLimits: SpeedLimits(car: 90, truck: 80, bus: 80, motorcycle: 90),
    centerline: [
        [43.269, 24.949],
        [43.280, 24.980],
        [43.292, 25.020],
        [43.300, 25.050],
        [43.308, 25.075]
    ],
    source: "tolltracker",
    lastVerified: "2026-04-12"
)

// Overlapping zone: same road as Trakiya T10 but opposite direction (east)
let TRAKIYA_T10_OPPOSITE = Zone(
    id: "trakiya-01-east",
    road: "АМ Тракия",
    roadLatin: "Trakiya",
    direction: "east",
    description: "Вакарел – Ихтиман",
    start: ZoneEndpoint(lat: 42.550, lng: 23.703, settlement: "Вакарел"),
    end: ZoneEndpoint(lat: 42.427, lng: 23.855, settlement: "Ихтиман"),
    distanceM: 19160,
    speedLimits: SpeedLimits(car: 140, truck: 90, bus: 100, motorcycle: 140),
    centerline: [
        [42.550, 23.703],
        [42.530, 23.740],
        [42.510, 23.770],
        [42.480, 23.800],
        [42.450, 23.830],
        [42.427, 23.855]
    ],
    source: "tolltracker",
    lastVerified: "2026-04-12"
)

// National road zone (not motorway, so standard 100m threshold applies).
let NATIONAL_ROAD_ZONE = Zone(
    id: "i1-01-east",
    road: "Път I-1",
    roadLatin: "I-1",
    direction: "east",
    description: "Test national road",
    start: ZoneEndpoint(lat: 42.700, lng: 23.400),
    end: ZoneEndpoint(lat: 42.710, lng: 23.500),
    distanceM: 8000,
    speedLimits: SpeedLimits(car: 90, truck: 80, bus: 80),
    centerline: [
        [42.700, 23.400],
        [42.705, 23.450],
        [42.710, 23.500]
    ],
    source: "test",
    lastVerified: "2026-04-12"
)

/// Generate a GPS trace along a zone's centerline at constant speed.
/// Includes 3 approach points before the zone start and 3 departure points after.
func generateGpsTrace(
    zone: Zone,
    speedKmh: Double,
    intervalMs: Int64 = 1000,
    startTime: Int64 = epochBase
) -> [GpsPoint] {
    var points: [GpsPoint] = []
    let centerline = zone.centerline
    if centerline.count < 2 { return points }

    var segLengths: [Double] = []
    var totalLength = 0.0
    for i in 0..<(centerline.count - 1) {
        let len = haversineDistance(
            centerline[i][0], centerline[i][1],
            centerline[i + 1][0], centerline[i + 1][1]
        )
        segLengths.append(len)
        totalLength += len
    }

    let speedMs = speedKmh / 3.6
    let distPerTick = speedMs * (Double(intervalMs) / 1000.0)

    // Approach points (3 points before zone start)
    let approachBearing = bearingBetween(
        centerline[1][0], centerline[1][1],
        centerline[0][0], centerline[0][1]
    )
    for i in stride(from: 3, through: 1, by: -1) {
        let offsetM = Double(i) * 200.0
        let offsetDegLat = (offsetM * cos(toRadians(approachBearing))) / 111_320.0
        let offsetDegLng = (offsetM * sin(toRadians(approachBearing)))
            / (111_320.0 * cos(toRadians(centerline[0][0])))
        let bearing = bearingBetween(
            centerline[0][0] + offsetDegLat, centerline[0][1] + offsetDegLng,
            centerline[0][0], centerline[0][1]
        )
        points.append(GpsPoint(
            lat: centerline[0][0] + offsetDegLat,
            lng: centerline[0][1] + offsetDegLng,
            speed: speedKmh,
            timestamp: startTime - Int64(i) * intervalMs,
            bearing: bearing
        ))
    }

    // Points along the centerline
    var currentDist = 0.0
    var segIdx = 0
    var segStart = 0.0
    var time = startTime

    while currentDist <= totalLength && segIdx < segLengths.count {
        let distInSeg = currentDist - segStart
        let t = segLengths[segIdx] > 0 ? distInSeg / segLengths[segIdx] : 0.0

        let lat = centerline[segIdx][0] + t * (centerline[segIdx + 1][0] - centerline[segIdx][0])
        let lng = centerline[segIdx][1] + t * (centerline[segIdx + 1][1] - centerline[segIdx][1])
        let bearing = bearingBetween(
            centerline[segIdx][0], centerline[segIdx][1],
            centerline[segIdx + 1][0], centerline[segIdx + 1][1]
        )

        points.append(GpsPoint(lat: lat, lng: lng, speed: speedKmh, timestamp: time, bearing: bearing))

        currentDist += distPerTick
        time += intervalMs

        while segIdx < segLengths.count && currentDist - segStart > segLengths[segIdx] {
            segStart += segLengths[segIdx]
            segIdx += 1
        }
    }

    // Departure points (3 points after zone end)
    let lastCl = centerline.last!
    let prevCl = centerline[centerline.count - 2]
    let exitBearing = bearingBetween(prevCl[0], prevCl[1], lastCl[0], lastCl[1])
    for i in 1...3 {
        time += intervalMs
        let offsetM = Double(i) * distPerTick
        let offsetDegLat = (offsetM * cos(toRadians(exitBearing))) / 111_320.0
        let offsetDegLng = (offsetM * sin(toRadians(exitBearing)))
            / (111_320.0 * cos(toRadians(lastCl[0])))
        points.append(GpsPoint(
            lat: lastCl[0] + offsetDegLat,
            lng: lastCl[1] + offsetDegLng,
            speed: speedKmh,
            timestamp: time,
            bearing: exitBearing
        ))
    }

    return points
}

/// Generate a GPS trace with a stop at the given fraction through the zone.
func generateTraceWithStop(
    zone: Zone,
    speedKmh: Double,
    stopAtFraction: Double = 0.5,
    stopDurationMs: Int64 = 120_000,
    intervalMs: Int64 = 1000,
    startTime: Int64 = epochBase
) -> [GpsPoint] {
    let fullTrace = generateGpsTrace(zone: zone, speedKmh: speedKmh, intervalMs: intervalMs, startTime: startTime)

    let approachCount = 3
    let zoneCount = max(0, fullTrace.count - approachCount - 3)
    let stopIdx = approachCount + Int(Double(zoneCount) * stopAtFraction)

    if stopIdx >= fullTrace.count { return fullTrace }

    let stopPoint = fullTrace[stopIdx]
    var result: [GpsPoint] = []

    result.append(contentsOf: fullTrace.prefix(stopIdx))

    let numStopPoints = Int(stopDurationMs / intervalMs)
    for i in 0..<numStopPoints {
        result.append(GpsPoint(
            lat: stopPoint.lat,
            lng: stopPoint.lng,
            speed: 0.0,
            timestamp: stopPoint.timestamp + Int64(i) * intervalMs,
            bearing: stopPoint.bearing
        ))
    }

    let timeShift = stopDurationMs
    for i in stopIdx..<fullTrace.count {
        let p = fullTrace[i]
        result.append(p.with(timestamp: p.timestamp + timeShift))
    }

    return result
}

/// Generate a GPS trace that exits the zone at a given fraction, goes off-road
/// for a given duration, then re-enters the same zone.
func generateReentryTrace(
    zone: Zone,
    speedKmh: Double,
    exitAtFraction: Double = 0.3,
    offRoadDurationMs: Int64 = 120_000,
    intervalMs: Int64 = 1000,
    startTime: Int64 = epochBase
) -> [GpsPoint] {
    let fullTrace = generateGpsTrace(zone: zone, speedKmh: speedKmh, intervalMs: intervalMs, startTime: startTime)
    let approachCount = 3
    let zoneCount = max(0, fullTrace.count - approachCount - 3)
    let exitIdx = approachCount + Int(Double(zoneCount) * exitAtFraction)

    if exitIdx >= fullTrace.count - 10 { return fullTrace }

    var result: [GpsPoint] = []
    result.append(contentsOf: fullTrace.prefix(exitIdx))

    let exitPoint = fullTrace[exitIdx]
    let offRoadCount = Int(offRoadDurationMs / intervalMs)
    let offsetLat = 0.003 // ~330m offset perpendicular
    for i in 0..<offRoadCount {
        result.append(GpsPoint(
            lat: exitPoint.lat + offsetLat,
            lng: exitPoint.lng,
            speed: 5.0,
            timestamp: exitPoint.timestamp + Int64(i) * intervalMs,
            bearing: exitPoint.bearing
        ))
    }

    let reentryTime = exitPoint.timestamp + offRoadDurationMs
    let timeShift = reentryTime - exitPoint.timestamp
    for i in exitIdx..<fullTrace.count {
        let p = fullTrace[i]
        result.append(p.with(timestamp: p.timestamp + timeShift))
    }

    return result
}

/// Add Gaussian noise to a GPS trace (deterministic for a given seed).
func addNoiseToTrace(
    _ trace: [GpsPoint],
    noiseMeters: Double = 5.0,
    seed: UInt64 = 42
) -> [GpsPoint] {
    var rng = SeededGaussianRNG(seed: seed)
    return trace.map { point in
        let noiseLat = (rng.nextGaussian() * noiseMeters) / 111_320.0
        let noiseLng = (rng.nextGaussian() * noiseMeters)
            / (111_320.0 * cos(toRadians(point.lat)))
        return point.with(
            lat: point.lat + noiseLat,
            lng: point.lng + noiseLng,
            accuracy: noiseMeters * 2
        )
    }
}

/// Generate a GPS trace with a GPS dropout (gap in timestamps) at the given fraction.
func generateTraceWithDropout(
    zone: Zone,
    speedKmh: Double,
    dropoutAtFraction: Double = 0.5,
    dropoutDurationMs: Int64 = 15_000,
    intervalMs: Int64 = 1000,
    startTime: Int64 = epochBase
) -> [GpsPoint] {
    let fullTrace = generateGpsTrace(zone: zone, speedKmh: speedKmh, intervalMs: intervalMs, startTime: startTime)

    let approachCount = 3
    let zoneCount = max(0, fullTrace.count - approachCount - 3)
    let dropoutIdx = approachCount + Int(Double(zoneCount) * dropoutAtFraction)

    if dropoutIdx >= fullTrace.count - 1 { return fullTrace }

    var result: [GpsPoint] = []
    result.append(contentsOf: fullTrace.prefix(dropoutIdx))

    let timeShift = dropoutDurationMs - intervalMs
    for i in dropoutIdx..<fullTrace.count {
        let p = fullTrace[i]
        result.append(p.with(timestamp: p.timestamp + timeShift))
    }

    return result
}

// Box–Muller Gaussian generator with a deterministic seed. Matches the spirit
// of `java.util.Random.nextGaussian()` in the Kotlin TestFixtures (different
// distribution implementation, identical statistical properties for our uses).
struct SeededGaussianRNG {
    private var state: UInt64
    private var spare: Double?

    init(seed: UInt64) {
        // Avoid zero state in xorshift64.
        self.state = seed == 0 ? 0xdead_beef_cafe_babe : seed
    }

    private mutating func nextUInt64() -> UInt64 {
        state ^= state << 13
        state ^= state >> 7
        state ^= state << 17
        return state
    }

    private mutating func nextDoubleOpenInterval() -> Double {
        // Returns a value in (0, 1); we exclude exact 0 so log() in Box–Muller stays finite.
        var x = nextUInt64()
        while x == 0 { x = nextUInt64() }
        return Double(x >> 11) / Double(UInt64(1) << 53)
    }

    mutating func nextGaussian() -> Double {
        if let s = spare {
            spare = nil
            return s
        }
        let u1 = nextDoubleOpenInterval()
        let u2 = nextDoubleOpenInterval()
        let mag = sqrt(-2.0 * log(u1))
        let z0 = mag * cos(2.0 * .pi * u2)
        let z1 = mag * sin(2.0 * .pi * u2)
        spare = z1
        return z0
    }
}
// swiftlint:enable identifier_name
