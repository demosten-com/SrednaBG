// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import SrednaBGCore

/// Position-delta speed inference. Mirrors the AAOS-emulator workaround in
/// `LocationTrackingService.kt` where FLP stamps a near-zero `speed` even
/// when positions move; we derive a speed from the haversine delta and use
/// `max(reported, derived)` so the real device path is unchanged.
public struct SpeedInference: Sendable {
    public static let minDistanceM: Double = 5.0
    public static let minDeltaSec: Double = 0.2
    public static let maxDeltaSec: Double = 30.0
    public static let maxInferredKmh: Double = 250.0

    public private(set) var lastInferredKmh: Double = 0
    public private(set) var lastTimestampMs: Int64 = 0
    public private(set) var lastLat: Double = .nan
    public private(set) var lastLng: Double = .nan

    public init() {}

    public mutating func combine(
        reportedKmh: Double,
        lat: Double,
        lng: Double,
        timestampMs: Int64
    ) -> Double {
        defer {
            lastTimestampMs = timestampMs
            lastLat = lat
            lastLng = lng
        }

        guard !lastLat.isNaN else { return reportedKmh }
        let deltaM = haversineDistance(lastLat, lastLng, lat, lng)
        let dtSec = Double(timestampMs - lastTimestampMs) / 1000.0
        guard deltaM >= Self.minDistanceM,
              dtSec >= Self.minDeltaSec,
              dtSec <= Self.maxDeltaSec
        else {
            return max(reportedKmh, lastInferredKmh)
        }
        let inferred = min((deltaM / dtSec) * 3.6, Self.maxInferredKmh)
        lastInferredKmh = inferred
        return max(reportedKmh, inferred)
    }

    public mutating func reset() {
        lastInferredKmh = 0
        lastTimestampMs = 0
        lastLat = .nan
        lastLng = .nan
    }
}

/// Bridges a CoreLocation-style fix into a core `GpsPoint`. CoreLocation is
/// not imported here so the type is testable on macOS / Linux; the iOS
/// `LocationTracker` populates `RawLocationFix` from a `CLLocation`.
public struct RawLocationFix: Sendable {
    public let lat: Double
    public let lng: Double
    public let course: Double?      // CLLocation.course (-1 → nil)
    public let speedMps: Double?    // CLLocation.speed   (-1 → nil)
    public let timestampMs: Int64
    public let accuracyM: Double?

    public init(
        lat: Double,
        lng: Double,
        course: Double?,
        speedMps: Double?,
        timestampMs: Int64,
        accuracyM: Double?
    ) {
        self.lat = lat
        self.lng = lng
        self.course = course
        self.speedMps = speedMps
        self.timestampMs = timestampMs
        self.accuracyM = accuracyM
    }
}

/// Stateful builder that derives bearing + speed and applies the GPS Kalman
/// filter. Designed to be owned by `ZoneTrackingService` (`@MainActor`) so it
/// runs synchronously per fix without an actor hop.
public struct GpsPointBuilder: Sendable {
    public private(set) var bearingFallback = BearingFallback()
    public private(set) var speedInference = SpeedInference()
    public private(set) var filter = GpsFilter()

    public init() {}

    /// Returns nil if no usable bearing is available yet (very first fix on a
    /// stationary device). Mirrors the `bearing.isNaN()` early-return in
    /// `LocationTrackingService.kt`: we publish position to UI but skip the
    /// zone detector to avoid false-matching on a default 0° heading.
    public mutating func build(_ raw: RawLocationFix) -> (point: GpsPoint, hasBearing: Bool) {
        let reportedKmh = (raw.speedMps ?? 0) * 3.6
        let speed = speedInference.combine(
            reportedKmh: max(reportedKmh, 0),
            lat: raw.lat,
            lng: raw.lng,
            timestampMs: raw.timestampMs
        )
        let bearing = bearingFallback.bearing(rawBearing: raw.course, lat: raw.lat, lng: raw.lng)
        let rawPoint = GpsPoint(
            lat: raw.lat,
            lng: raw.lng,
            speed: speed,
            timestamp: raw.timestampMs,
            bearing: bearing ?? 0,
            accuracy: raw.accuracyM
        )
        let filtered = filter.filter(rawPoint)
        return (filtered, bearing != nil)
    }

    public mutating func reset() {
        bearingFallback.reset()
        speedInference.reset()
        filter.reset()
    }
}
