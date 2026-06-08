// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

/// Stateful zone-tracking state machine. Mutating value type — embed inside
/// `ZoneTrackingService` (a `@MainActor @Observable` class) so the GPS-consumer
/// task mutates it without `await` per sample.
///
/// `update(_:vehicleType:)` honors the driver's selected vehicle type when
/// looking up the speed limit (Android's `ZoneDetector` matches this).
public struct ZoneDetector: Sendable {
    public static let maxRoadDistanceM = 100.0
    public static let directionToleranceDeg = 45.0
    public static let entryDistanceM = 500.0
    // Declare the zone finished once within this straight-line distance of the
    // end — by here the end camera is in sight, but the average + remainder
    // guidance stayed live through almost the whole zone. Relies on the
    // centerline actually reaching `zone.end` (the scraper aligns it), so this
    // trips cleanly near the real end rather than hundreds of metres short.
    // Matches Android's `EXIT_DISTANCE_M`.
    public static let exitDistanceM = 100.0
    public static let stopSpeedKmh = 5.0
    public static let stopDurationMs: Int64 = 30_000
    public static let gpsDropoutMs: Int64 = 10_000

    // Off-road exit hysteresis. A single off-road fix is usually a transient
    // GPS/Kalman blip — the smoothed position lags the road on a bend (worse on
    // coarsely-sampled centerlines), or a momentary glitch (overpass, tunnel
    // mouth, urban canyon) throws one fix wide. Exiting on the first such fix
    // produces a spurious Exiting → InZone flap. So require the off-road
    // condition to persist this many consecutive fixes before declaring an exit;
    // a genuine off-ramp diverges steadily and trips it within a few seconds.
    // Mirrors Android's `OFF_ROAD_EXIT_GRACE_FIXES`.
    public static let offRoadExitGraceFixes = 3
    // …unless the fix is this far off the centerline, which is no blip but a
    // real departure (different road / GPS teleport) — exit immediately.
    public static let offRoadHardM = 1000.0

    public private(set) var state: ZoneState = .outside

    // Orient every zone's centerline to run start → end once, up front, so all
    // the order-dependent geometry below (direction matching, polyline
    // projection, remaining distance, puck snapping) is correct regardless of
    // how the source stored the points. A centerline stored end-first — a real
    // server-data bug — would otherwise flip a zone's apparent direction. The
    // start/end endpoints are authoritative, so orienting to them makes the
    // engine immune to the bad point order. NOTE: orient at this detector
    // boundary, NOT as a stored/lazy property on `Zone` — `Zone` round-trips
    // through `Codable` and a derived stored field breaks (de)serialization
    // (matches the Kotlin note).
    private let zones: [Zone]
    private var lastPoint: GpsPoint?
    private var activeZone: Zone?
    private var entryTime: Int64 = 0
    private var distanceTraveled: Double = 0
    private var effectiveZoneDistance: Double = 0
    private var totalStopDurationMs: Int64 = 0
    private var stopStartTime: Int64?
    private var offRoadStreak = 0

    public init(zones: [Zone]) {
        self.zones = zones.map { $0.with(centerline: orientCenterlineToStart($0.centerline, $0.start)) }
    }

    @discardableResult
    public mutating func update(_ point: GpsPoint, vehicleType: VehicleType = .car) -> ZoneState {
        let newState: ZoneState
        switch state {
        case .outside: newState = handleOutside(point, vehicleType: vehicleType)
        case .inZone: newState = handleInZone(point, vehicleType: vehicleType)
        case .exiting: newState = handleExiting(point, vehicleType: vehicleType)
        }
        state = newState
        lastPoint = point
        return newState
    }

    public mutating func reset() {
        state = .outside
        lastPoint = nil
        activeZone = nil
        entryTime = 0
        distanceTraveled = 0
        effectiveZoneDistance = 0
        totalStopDurationMs = 0
        stopStartTime = nil
        offRoadStreak = 0
    }

    private mutating func handleOutside(_ point: GpsPoint, vehicleType: VehicleType) -> ZoneState {
        guard let zone = RoadMatcher.findMatchingZone(point, zones) else { return .outside }
        let distToStart = RoadMatcher.distanceToZoneStart(point, zone)
        let distToEnd = RoadMatcher.distanceToZoneEnd(point, zone)
        let remaining = polylineRemaining(point, zone)

        let nearStart = distToStart <= Self.entryDistanceM
        // Cold-start mid-zone: on the road, heading matches, past the entry buffer,
        // with meaningful road still ahead. Gate on the polyline remainder (a point
        // just past the end still in the road-width band has ~0 remaining and must
        // NOT re-enter the just-completed zone), AND require it to be more than the
        // exit distance from the end — a centerline that hooks/overshoots at its
        // tail can make `projectOntoPolyline` snap a just-exited point back onto an
        // earlier leg and report a large `remaining`, briefly re-admitting the zone
        // we are exiting (Exiting → InZone → Exiting flap on the final ~100 m). The
        // straight-line `distToEnd` clause closes that. Mirrors Android.
        let midZone = !nearStart && remaining > Self.exitDistanceM && distToEnd > Self.exitDistanceM

        if !nearStart && !midZone {
            return .outside
        }

        activeZone = zone
        entryTime = point.timestamp
        distanceTraveled = 0
        totalStopDurationMs = 0
        stopStartTime = nil
        offRoadStreak = 0
        // Full zone if approached from start; remaining polyline arc-length to the
        // end if joined mid-zone (avg speed is measured from here). Use the
        // polyline remainder — not the straight-line distToEnd — so the legal-time
        // budget matches the road actually left to drive.
        effectiveZoneDistance = nearStart ? Double(zone.distanceM) : remaining

        let status = AverageSpeedCalc.calculate(
            entryTime: entryTime,
            currentTime: point.timestamp,
            stopDurationMs: totalStopDurationMs,
            distanceTraveled: distanceTraveled,
            zoneDistance: effectiveZoneDistance,
            speedLimitKmh: vehicleType.limit(zone.speedLimits)
        )

        return .inZone(.init(
            zone: zone,
            entryTime: entryTime,
            distanceTraveled: distanceTraveled,
            avgSpeed: status.avgSpeed,
            speedStatus: status,
            distanceRemaining: remaining
        ))
    }

    private mutating func handleInZone(_ point: GpsPoint, vehicleType: VehicleType) -> ZoneState {
        guard let zone = activeZone else { return .outside }

        // Accumulate distance via speed × elapsed time (trapezoidal). Position
        // estimates may lag the true vehicle position when the Kalman filter is
        // sluggish; reported GPS speed is Doppler-derived and tracks the truth
        // far better. Skip on GPS dropout to avoid phantom distance.
        if let prev = lastPoint {
            let gap = point.timestamp - prev.timestamp
            if gap >= 1 && gap < Self.gpsDropoutMs {
                let gapSec = Double(gap) / 1000.0
                let avgSpeedMs = ((prev.speed + point.speed) / 2.0) / 3.6
                distanceTraveled += avgSpeedMs * gapSec
            }
        }

        updateStopTracking(point)

        // Accurate live distance to the zone end from the polyline projection —
        // drift-free, unlike the speed×time integrator above. Drives the exit
        // decision, the user-facing remaining label, and the remainder-speed math
        // so integrator drift (or unevenly-spaced simulated fixes) can't fake an
        // early "overshot the end" exit or collapse the remainder to 0 mid-zone.
        let remaining = polylineRemaining(point, zone)

        // Check exit conditions. Use the zone-appropriate on-road band (the
        // motorway override widens it to 150 m) — the same band entry matching
        // uses. A single off-road fix is treated as a transient blip: only exit
        // once it persists `offRoadExitGraceFixes` fixes, or immediately when the
        // fix is `offRoadHardM` past the road (a real departure, not a blip).
        if !RoadMatcher.isOnRoad(point, zone) {
            offRoadStreak += 1
            let farGone = RoadMatcher.distanceToCenterline(point, zone) > Self.offRoadHardM
            if farGone || offRoadStreak >= Self.offRoadExitGraceFixes {
                return exitZone(point, zone, vehicleType: vehicleType)
            }
            // Within the grace window — stay in the zone and keep guidance live.
        } else {
            offRoadStreak = 0
        }
        if RoadMatcher.distanceToZoneEnd(point, zone) < Self.exitDistanceM {
            return exitZone(point, zone, vehicleType: vehicleType)
        }
        // Reached the polyline end (e.g. zone end point offset from the road so the
        // haversine check above never trips). Position-based backstop, replacing
        // the old `distanceTraveled >= distanceM * 1.1` integrator check that
        // drifted on simulated/noisy traces.
        if remaining <= 0 {
            return exitZone(point, zone, vehicleType: vehicleType)
        }

        let status = AverageSpeedCalc.calculate(
            entryTime: entryTime,
            currentTime: point.timestamp,
            stopDurationMs: totalStopDurationMs,
            distanceTraveled: distanceTraveled,
            zoneDistance: effectiveZoneDistance,
            speedLimitKmh: vehicleType.limit(zone.speedLimits),
            distanceRemainingOverride: remaining
        )

        return .inZone(.init(
            zone: zone,
            entryTime: entryTime,
            distanceTraveled: distanceTraveled,
            avgSpeed: status.avgSpeed,
            speedStatus: status,
            distanceRemaining: remaining
        ))
    }

    private mutating func handleExiting(_ point: GpsPoint, vehicleType: VehicleType) -> ZoneState {
        resetTrackingState()
        return handleOutside(point, vehicleType: vehicleType)
    }

    private mutating func exitZone(_ point: GpsPoint, _ zone: Zone, vehicleType: VehicleType) -> ZoneState {
        finalizeStop(currentTime: point.timestamp)
        let status = AverageSpeedCalc.calculate(
            entryTime: entryTime,
            currentTime: point.timestamp,
            stopDurationMs: totalStopDurationMs,
            distanceTraveled: distanceTraveled,
            zoneDistance: effectiveZoneDistance,
            speedLimitKmh: vehicleType.limit(zone.speedLimits)
        )
        return .exiting(.init(zone: zone, finalAvgSpeed: status.avgSpeed))
    }

    private mutating func updateStopTracking(_ point: GpsPoint) {
        if point.speed < Self.stopSpeedKmh {
            if stopStartTime == nil {
                stopStartTime = point.timestamp
            }
        } else {
            finalizeStop(currentTime: point.timestamp)
        }
    }

    private mutating func finalizeStop(currentTime: Int64) {
        guard let start = stopStartTime else { return }
        let duration = currentTime - start
        if duration >= Self.stopDurationMs {
            totalStopDurationMs += duration
        }
        stopStartTime = nil
    }

    private mutating func resetTrackingState() {
        activeZone = nil
        entryTime = 0
        distanceTraveled = 0
        effectiveZoneDistance = 0
        totalStopDurationMs = 0
        stopStartTime = nil
        offRoadStreak = 0
    }

    // Polyline arc-length from the current GPS position to zone.end. Drives the
    // "X km" label and progress bar — uses the live position rather than the
    // speed×time integrator so it stays accurate across GPS dropouts, mid-zone
    // cold-starts, and simulated jumps. Mirrors Android's `polylineRemaining`.
    private func polylineRemaining(_ point: GpsPoint, _ zone: Zone) -> Double {
        let traveledOnPolyline = projectOntoPolyline(point.lat, point.lng, zone.centerline)
        // Measure against the centerline's own arc length, not the official
        // `zone.distanceM`, so "remaining" is exactly 0 at the polyline end
        // regardless of any drift between the two (matches Android).
        return max(polylineLengthMeters(zone.centerline) - traveledOnPolyline, 0.0)
    }
}
