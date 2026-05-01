// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

public enum AverageSpeedCalc {
    // Suppress avg speed until we have this much active tracking — distance/time
    // is noisy in the sub-second window and would briefly flash "0" on entry.
    private static let minActiveSec = 1.0

    // Cap the displayed "max for remainder" — near zone end the quotient blows up
    // (and goes infinite once the legal time is exhausted), which surfaces as
    // 500 / 1000+ km/h jitter in the UI.
    private static let maxRemainderSpeedKmh = 250.0

    public static func calculate(
        entryTime: Int64,
        currentTime: Int64,
        stopDurationMs: Int64,
        distanceTraveled: Double,
        zoneDistance: Double,
        speedLimitKmh: Int
    ) -> SpeedStatus {
        let elapsedMs = currentTime - entryTime
        let elapsedSec = Double(elapsedMs) / 1000.0
        let stopSec = Double(stopDurationMs) / 1000.0
        let activeSec = max(elapsedSec - stopSec, 0.0)

        let avgSpeedKmh: Double? = activeSec >= minActiveSec
            ? (distanceTraveled / activeSec) * 3.6
            : nil

        let distanceRemaining = max(zoneDistance - distanceTraveled, 0.0)

        let speedLimitMs = Double(speedLimitKmh) / 3.6
        let requiredTotalSec = speedLimitMs > 0 ? zoneDistance / speedLimitMs : 0.0
        let timeRemainingSec = requiredTotalSec - activeSec

        let maxSpeedKmh: Double
        if distanceRemaining <= 0 {
            maxSpeedKmh = 0
        } else if timeRemainingSec <= 0 {
            maxSpeedKmh = Self.maxRemainderSpeedKmh
        } else {
            maxSpeedKmh = min((distanceRemaining / timeRemainingSec) * 3.6, Self.maxRemainderSpeedKmh)
        }

        return SpeedStatus(
            avgSpeed: avgSpeedKmh,
            maxSpeedForRemainder: maxSpeedKmh,
            distanceRemaining: distanceRemaining,
            timeRemaining: timeRemainingSec,
            isOverLimit: avgSpeedKmh.map { $0 > Double(speedLimitKmh) } ?? false
        )
    }
}
