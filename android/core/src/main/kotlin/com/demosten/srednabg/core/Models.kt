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

/**
 * A single GPS fix fed into the engine.
 *
 * @property lat latitude in decimal degrees (WGS84).
 * @property lng longitude in decimal degrees (WGS84).
 * @property speed ground speed in **km/h** (the engine divides by 3.6 where it
 *   needs m/s — never assume m/s).
 * @property timestamp fix time as epoch **milliseconds**.
 * @property bearing course over ground in **degrees** clockwise from true north,
 *   `[0, 360)`.
 * @property accuracy horizontal accuracy radius in **metres**, or null when the
 *   provider reports none.
 */
data class GpsPoint(
    val lat: Double,
    val lng: Double,
    val speed: Double,
    val timestamp: Long,
    val bearing: Double,
    val accuracy: Double? = null,
)

/**
 * Derived running-average speed status for the active zone.
 *
 * @property avgSpeed running average over the zone so far in **km/h**, or null
 *   until enough active tracking has accumulated.
 * @property maxSpeedForRemainder the highest sustainable average for the rest of
 *   the zone that still finishes legal, in **km/h**.
 * @property distanceRemaining road left to the zone end in **metres**.
 * @property timeRemaining legal time budget left for the remainder in **seconds**
 *   (may be negative once the budget is exhausted).
 * @property isOverLimit true when [avgSpeed] already exceeds the effective limit.
 */
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
        val speedStatus: SpeedStatus,
        // Polyline arc-length to zone.end from the live GPS position — drives
        // the user-facing label and progress bar. Distinct from
        // speedStatus.distanceRemaining, which is relative to effectiveZoneDistance
        // and the speed×time integrator (used by the avg-speed math).
        val distanceRemaining: Double,
    ) : ZoneState() {
        // Convenience alias — the running average always lives in speedStatus.
        // Kept as a derived property so the two can never disagree.
        val avgSpeed: Double? get() = speedStatus.avgSpeed
    }

    /**
     * Inside a zone whose entry we did not witness, so no measurement is
     * possible: we cannot know what the entry camera timestamped, and a running
     * average over the remainder alone matches nothing BG TOLL computes.
     *
     * Carries only facts about the road — the zone (and therefore its speed
     * limit) and the distance left to drive, both true regardless of when we
     * joined. It deliberately carries **no** timing or averaging fields, and
     * that is structural rather than a convention: there is no average here to
     * accidentally render.
     *
     * Two invariants consumers may rely on:
     * - [Exiting] only ever follows [InZone]. An [Unmeasured] zone has no
     *   traversal to finalize, so leaving one goes straight to [Outside] — no
     *   History row, no exit announcement, nothing to suppress downstream.
     * - `Unmeasured -> InZone` is unreachable for the same zone: arc length only
     *   increases, so a start cannot be witnessed retroactively.
     *
     * See ZoneDetector.START_WITNESS_ARC_M.
     */
    data class Unmeasured(
        val zone: Zone,
        // Polyline arc-length to zone.end from the live GPS position, same
        // meaning as InZone.distanceRemaining.
        val distanceRemaining: Double,
    ) : ZoneState()

    data class Exiting(
        val zone: Zone,
        val finalAvgSpeed: Double?,
    ) : ZoneState()
}
