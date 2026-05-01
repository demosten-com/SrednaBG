// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

data class ZoneEndpoint(
    val lat: Double,
    val lng: Double,
    val kmMarker: String? = null,
    val settlement: String? = null,
    val settlementLatin: String? = null,
)

data class SpeedLimits(
    val car: Int,
    val truck: Int,
    val bus: Int,
    val motorcycle: Int? = null,
)

data class Zone(
    val id: String,
    val road: String,
    val roadLatin: String? = null,
    val direction: String,
    val description: String,
    val start: ZoneEndpoint,
    val end: ZoneEndpoint,
    val distanceM: Int,
    val speedLimits: SpeedLimits,
    val centerline: List<List<Double>>,
    val source: String,
    val lastVerified: String,
)

data class GpsPoint(
    val lat: Double,
    val lng: Double,
    val speed: Double,
    val timestamp: Long,
    val bearing: Double,
    val accuracy: Double? = null,
)

data class SpeedStatus(
    val avgSpeed: Double?,
    val maxSpeedForRemainder: Double,
    val distanceRemaining: Double,
    val timeRemaining: Double,
    val isOverLimit: Boolean,
)

sealed class ZoneState {
    data object Outside : ZoneState()

    data class InZone(
        val zone: Zone,
        val entryTime: Long,
        val distanceTraveled: Double,
        val avgSpeed: Double?,
        val speedStatus: SpeedStatus,
        // Polyline arc-length to zone.end from the live GPS position — drives
        // the user-facing label and progress bar. Distinct from
        // speedStatus.distanceRemaining, which is relative to effectiveZoneDistance
        // and the speed×time integrator (used by the avg-speed math).
        val distanceRemaining: Double,
    ) : ZoneState()

    data class Exiting(
        val zone: Zone,
        val finalAvgSpeed: Double?,
    ) : ZoneState()
}
