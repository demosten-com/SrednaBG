// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import SrednaBGCore

/// Reproduces the bearing fallback in `LocationTrackingService.kt`. A
/// `CLLocation` reports `course = -1` when the device can't compute a bearing
/// (stationary, just woken up, simulator without a route). When the position
/// has moved at least `minDeltaM`, derive the bearing from the position
/// delta; otherwise hold the last known one.
public struct BearingFallback: Sendable {
    public static let minDeltaM: Double = 5.0

    public private(set) var lastBearing: Double?
    public private(set) var lastLat: Double?
    public private(set) var lastLng: Double?

    public init() {}

    /// Returns the bearing to use for this fix, optionally updating internal
    /// state. Mutating because we cache the previous position + bearing.
    ///
    /// `freshFix` gates the position-seed (`lastLat`/`lastLng`) update: a stale
    /// CoreLocation "last known" fix must NOT seed the position, or the next
    /// fresh fix would derive a bearing from a stale→fresh delta (possibly the
    /// wrong direction → false zone match). Mirrors Android's freshFix-gated
    /// `lastRawLat/Lng` update and `SpeedInference.combine`'s `freshFix` guard.
    public mutating func bearing(
        rawBearing: Double?,
        lat: Double,
        lng: Double,
        freshFix: Bool = true
    ) -> Double? {
        let result: Double?
        if let raw = rawBearing, raw.isFinite, raw >= 0 {
            lastBearing = raw
            result = raw
        } else if let pLat = lastLat, let pLng = lastLng,
                  haversineDistance(pLat, pLng, lat, lng) >= Self.minDeltaM {
            let derived = bearingBetween(pLat, pLng, lat, lng)
            lastBearing = derived
            result = derived
        } else {
            result = lastBearing
        }
        if freshFix {
            lastLat = lat
            lastLng = lng
        }
        return result
    }

    public mutating func reset() {
        lastBearing = nil
        lastLat = nil
        lastLng = nil
    }
}
