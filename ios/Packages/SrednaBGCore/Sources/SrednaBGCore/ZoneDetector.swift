// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

/// Stateful zone-tracking state machine. Mutating value type — embed inside
/// `ZoneTrackingService` (a `@MainActor @Observable` class) so the GPS-consumer
/// task mutates it without `await` per sample.
///
/// The Swift `vehicleType` parameter is the iOS bug-fix: Android's
/// `ZoneDetector` hardcodes `zone.speedLimits.car`, ignoring the user's
/// vehicle-type setting. TODO to backport to Kotlin.
public struct ZoneDetector: Sendable {
    public static let maxRoadDistanceM = 100.0
    public static let directionToleranceDeg = 45.0
    public static let entryDistanceM = 500.0
    public static let exitDistanceM = 300.0
    public static let stopSpeedKmh = 5.0
    public static let stopDurationMs: Int64 = 30_000
    public static let gpsDropoutMs: Int64 = 10_000

    public private(set) var state: ZoneState = .outside

    private let zones: [Zone]
    private var lastPoint: GpsPoint?
    private var activeZone: Zone?
    private var entryTime: Int64 = 0
    private var distanceTraveled: Double = 0
    private var effectiveZoneDistance: Double = 0
    private var totalStopDurationMs: Int64 = 0
    private var stopStartTime: Int64?

    public init(zones: [Zone]) {
        self.zones = zones
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
    }

    private mutating func handleOutside(_ point: GpsPoint, vehicleType: VehicleType) -> ZoneState {
        guard let zone = RoadMatcher.findMatchingZone(point, zones) else { return .outside }
        let distToStart = RoadMatcher.distanceToZoneStart(point, zone)
        let distToEnd = RoadMatcher.distanceToZoneEnd(point, zone)

        let nearStart = distToStart <= Self.entryDistanceM
        // Cold-start mid-zone: on the road, heading matches, past the entry buffer,
        // and not already about to exit.
        let midZone = !nearStart && distToEnd > Self.exitDistanceM

        if !nearStart && !midZone {
            return .outside
        }

        activeZone = zone
        entryTime = point.timestamp
        distanceTraveled = 0
        totalStopDurationMs = 0
        stopStartTime = nil
        effectiveZoneDistance = nearStart ? Double(zone.distanceM) : distToEnd

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
            distanceRemaining: status.distanceRemaining
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

        if !RoadMatcher.isOnRoad(point, zone, maxDistance: Self.maxRoadDistanceM) {
            return exitZone(point, zone, vehicleType: vehicleType)
        }
        if RoadMatcher.distanceToZoneEnd(point, zone) < Self.exitDistanceM {
            return exitZone(point, zone, vehicleType: vehicleType)
        }
        if distanceTraveled >= Double(zone.distanceM) * 1.1 {
            return exitZone(point, zone, vehicleType: vehicleType)
        }

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
            distanceRemaining: status.distanceRemaining
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
    }
}
