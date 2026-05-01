// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import kotlin.math.max

object AverageSpeedCalc {

    // Suppress avg speed until we have this much active tracking — distance/time
    // is noisy in the sub-second window and would briefly flash "0" on entry.
    private const val MIN_ACTIVE_SEC = 1.0

    // Cap the displayed "max for remainder" — near zone end the quotient blows up
    // (and goes infinite once the legal time is exhausted), which surfaces as
    // 500 / 1000+ km/h jitter in the UI.
    private const val MAX_REMAINDER_SPEED_KMH = 250.0

    fun calculate(
        entryTime: Long,
        currentTime: Long,
        stopDurationMs: Long,
        distanceTraveled: Double,
        zoneDistance: Double,
        speedLimitKmh: Int,
    ): SpeedStatus {
        val elapsedMs = currentTime - entryTime
        val elapsedSec = elapsedMs / 1000.0
        val stopSec = stopDurationMs / 1000.0
        val activeSec = max(elapsedSec - stopSec, 0.0)

        val avgSpeedKmh: Double? = if (activeSec >= MIN_ACTIVE_SEC) {
            (distanceTraveled / activeSec) * 3.6
        } else null

        val distanceRemaining = max(zoneDistance - distanceTraveled, 0.0)

        val speedLimitMs = speedLimitKmh / 3.6
        val requiredTotalSec = if (speedLimitMs > 0) zoneDistance / speedLimitMs else 0.0
        val timeRemainingSec = requiredTotalSec - activeSec

        // Max speed for remainder to stay legal
        val maxSpeedKmh = when {
            distanceRemaining <= 0 -> 0.0
            timeRemainingSec <= 0 -> MAX_REMAINDER_SPEED_KMH
            else -> minOf((distanceRemaining / timeRemainingSec) * 3.6, MAX_REMAINDER_SPEED_KMH)
        }

        return SpeedStatus(
            avgSpeed = avgSpeedKmh,
            maxSpeedForRemainder = maxSpeedKmh,
            distanceRemaining = distanceRemaining,
            timeRemaining = timeRemainingSec,
            isOverLimit = avgSpeedKmh != null && avgSpeedKmh > speedLimitKmh,
        )
    }
}
