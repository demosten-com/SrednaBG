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

/// A zone co-located with `base`: its start sits exactly on `base`'s end and its
/// centerline runs straight on from there along `base`'s final heading. Models
/// the back-to-back camera pairs in the real data (24 of them, nearly all with
/// the two endpoints 0 m apart). Mirrors Kotlin `nextZoneFrom`.
func nextZoneFrom(_ base: Zone, id: String, lengthM: Double) -> Zone {
    let cl = base.centerline
    let heading = bearingBetween(
        cl[cl.count - 2][0], cl[cl.count - 2][1], cl[cl.count - 1][0], cl[cl.count - 1][1]
    )
    let stepM = 100.0
    let points = (0...Int(lengthM / stepM)).map { i -> [Double] in
        let d = Double(i) * stepM
        return [
            base.end.lat + (d * cos(heading * .pi / 180)) / 111_320.0,
            base.end.lng + (d * sin(heading * .pi / 180)) /
                (111_320.0 * cos(base.end.lat * .pi / 180))
        ]
    }
    return Zone(
        id: id,
        road: base.road,
        roadLatin: base.roadLatin,
        direction: base.direction,
        description: base.description,
        start: ZoneEndpoint(lat: base.end.lat, lng: base.end.lng),
        end: ZoneEndpoint(lat: points[points.count - 1][0], lng: points[points.count - 1][1]),
        distanceM: Int(lengthM),
        speedLimits: base.speedLimits,
        centerline: points,
        source: base.source,
        lastVerified: base.lastVerified
    )
}

// A straight synthetic road for the ISSUE-001 jog fixture below.
let jogZoneHeadingDeg = 37.0
private let jogZoneOriginLat = 42.2
private let jogZoneOriginLng = 23.1

/// `metres` along `headingDeg` from a lat/lng, as a `[lat, lng]` pair.
private func offsetMetres(_ lat: Double, _ lng: Double, _ headingDeg: Double, _ metres: Double) -> [Double] {
    let rad = headingDeg * .pi / 180
    return [
        lat + (metres * cos(rad)) / 111_320.0,
        lng + (metres * sin(rad)) / (111_320.0 * cos(lat * .pi / 180))
    ]
}

/// Position for an arc length that may be **negative**, i.e. on the approach
/// road before the entry camera. Negative arcs extrapolate straight back from
/// the centerline's first vertex along `heading`, which is what a car driving up
/// to the camera actually does.
///
/// This matters because entry provenance is now decided by the arc position of
/// the *first* matching fix (`ZoneDetector.startWitnessArcM`): a trace that
/// simply starts mid-zone is a "joined late" drive and is deliberately
/// unmeasured, so any test that means "a car genuinely driving this zone" has to
/// begin before arc 0. Mirrors Kotlin `pointOnApproach`.
///
/// Not private: it is load-bearing enough for the entry-provenance suite to
/// deserve its own assertions (see `TestFixturesTests`), rather than only being
/// exercised indirectly through `collectAlongCenterline`.
func pointOnApproach(_ zone: Zone, _ arc: Double, _ heading: Double) -> [Double] {
    if arc >= 0 { return pointAtArcLength(zone.centerline, arc) }
    let v0 = zone.centerline[0]
    let back = (heading + 180).truncatingRemainder(dividingBy: 360) * .pi / 180
    return [
        v0[0] + (-arc * cos(back)) / 111_320.0,
        v0[1] + (-arc * sin(back)) / (111_320.0 * cos(v0[0] * .pi / 180))
    ]
}

/// A zone whose stored centerline opens with a segment running ~180 degrees
/// *against* the road: `centerline[0]` is the entry camera, `centerline[1]` sits
/// `jogM` metres **behind** it, and only then does the geometry run forward.
///
/// This is ISSUE-001 as it appears in the shipped data — i3-02-north (121 m jog),
/// i6-01-east (80 m) and trakiya-03-east (77 m). It matters here because a car
/// approaching the camera projects onto that backwards leg, so the arc position
/// of its *first* matching fix is the jog length rather than ~0. Measured across
/// all 72 bundled zones, the worst such value is 121 m at the 2 s near-zone
/// cadence and 148 m at the 5 s cold-start cadence — which is why
/// `ZoneDetector.startWitnessArcM` is 200 m and not the 100 m first proposed.
///
/// A national road (not "АМ …"), so it gets the stricter 100 m on-road band.
/// Mirrors Kotlin `jogStartZone`.
func jogStartZone(
    id: String = "jog-start-test",
    jogM: Double = 121.0,
    lengthM: Double = 8_000.0
) -> Zone {
    let origin = [jogZoneOriginLat, jogZoneOriginLng]
    let end = offsetMetres(origin[0], origin[1], jogZoneHeadingDeg, lengthM)
    let stepM = 100.0
    // centerline[0] is the camera; centerline[1] is jogM behind it; from there the
    // geometry runs forward, back past the camera and on to the zone end. The
    // final step is clamped to lengthM so the last vertex lands exactly on `end`
    // — a bare floor() count stops up to stepM short, leaving centerline.last()
    // and zone.end disagreeing by tens of metres. Mirrors Kotlin.
    let steps = Int(((jogM + lengthM) / stepM).rounded(.up))
    let forward = (1...steps).map { i -> [Double] in
        offsetMetres(origin[0], origin[1], jogZoneHeadingDeg, min(-jogM + Double(i) * stepM, lengthM))
    }
    return Zone(
        id: id,
        road: "Път I-3",
        roadLatin: "I-3",
        direction: "north",
        description: "ISSUE-001 backwards start jog",
        start: ZoneEndpoint(lat: origin[0], lng: origin[1]),
        end: ZoneEndpoint(lat: end[0], lng: end[1]),
        distanceM: Int(lengthM),
        speedLimits: SpeedLimits(car: 90, truck: 80, bus: 80, motorcycle: 90),
        centerline: [origin, offsetMetres(origin[0], origin[1], jogZoneHeadingDeg, -jogM)] + forward,
        source: "test",
        lastVerified: "2026-07-28"
    )
}

/// Fixes along the straight *physical* road of `jogStartZone`, from `fromM` to
/// `toM` metres relative to the entry camera (negative = still approaching).
///
/// The shared `collectAlongCenterline` cannot be used here: it derives its
/// heading from the stored geometry, which for this zone points backwards near
/// arc 0 — the whole point of the fixture. Mirrors Kotlin `jogStartRoadTrace`.
func jogStartRoadTrace(
    fromM: Double,
    toM: Double,
    stepM: Double = 36.0,
    speedKmh: Double = 90.0,
    startTime: Int64 = epochBase
) -> [GpsPoint] {
    let stepMs = max(Int64(stepM / (speedKmh / 3.6) * 1000.0), 1)
    var points: [GpsPoint] = []
    var d = fromM
    var i: Int64 = 0
    while d <= toM {
        let at = offsetMetres(jogZoneOriginLat, jogZoneOriginLng, jogZoneHeadingDeg, d)
        points.append(GpsPoint(
            lat: at[0], lng: at[1], speed: speedKmh,
            timestamp: startTime + i * stepMs, bearing: jogZoneHeadingDeg
        ))
        d += stepM
        i += 1
    }
    return points
}

/// Drive `detector` along `zone`'s centerline for `metres`, starting `fromArcM`
/// along it, and return every state it produced.
///
/// Each fix carries the road's local heading, so it reads as a car genuinely
/// following the road — which is what entry confirmation
/// (`ZoneDetector.entryConfirmDistanceM`) asks for. `lateralOffsetM` pushes the
/// track sideways off the centerline for off-road cases.
/// Mirrors Kotlin `collectAlongCenterline`.
@discardableResult
func collectAlongCenterline(
    _ detector: inout ZoneDetector,
    _ zone: Zone,
    fromArcM: Double,
    metres: Double,
    speedKmh: Double = 130.0,
    stepM: Double = 36.0,
    startTime: Int64 = epochBase,
    lateralOffsetM: Double = 0,
    vehicleType: VehicleType = .car
) -> [ZoneState] {
    centerlineTrace(
        zone, fromArcM: fromArcM, metres: metres, speedKmh: speedKmh,
        stepM: stepM, startTime: startTime, lateralOffsetM: lateralOffsetM
    ).map { detector.update($0, vehicleType: vehicleType) }
}

/// The GPS trace `collectAlongCenterline` drives, without a detector.
///
/// Split out so a test that needs to inspect the detector *between* fixes — the
/// entry-candidate side channel, `ZoneDetector.pendingEntryInfo`, which is not a
/// `ZoneState` and so cannot be read from the returned list — drives exactly the
/// same geometry as every other test here rather than hand-rolling a lookalike.
/// Mirrors Kotlin `centerlineTrace`.
func centerlineTrace(
    _ zone: Zone,
    fromArcM: Double,
    metres: Double,
    speedKmh: Double = 130.0,
    stepM: Double = 36.0,
    startTime: Int64 = epochBase,
    lateralOffsetM: Double = 0
) -> [GpsPoint] {
    var points: [GpsPoint] = []
    var covered = 0.0
    var index: Int64 = 0
    let stepMs = max(Int64(stepM / (speedKmh / 3.6) * 1000.0), 1)
    while covered <= metres {
        let arc = fromArcM + covered
        let heading = localPolylineBearing(zone.centerline, max(arc, 0), RoadMatcher.localBearingWindowM)
            ?? polylineBearing(zone.centerline) ?? 0
        let at = pointOnApproach(zone, arc, heading)
        // Offset perpendicular (to the right of travel) by lateralOffsetM.
        let perp = (heading + 90).truncatingRemainder(dividingBy: 360) * .pi / 180
        let lat = at[0] + (lateralOffsetM * cos(perp)) / 111_320.0
        let lng = at[1] + (lateralOffsetM * sin(perp)) / (111_320.0 * cos(at[0] * .pi / 180))
        points.append(GpsPoint(
            lat: lat, lng: lng, speed: speedKmh,
            timestamp: startTime + index * stepMs, bearing: heading
        ))
        covered += stepM
        index += 1
    }
    return points
}

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
