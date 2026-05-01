// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

class ZoneDetector(private val zones: List<Zone>) {

    companion object {
        const val MAX_ROAD_DISTANCE_M = 100.0
        const val DIRECTION_TOLERANCE_DEG = 45.0
        const val ENTRY_DISTANCE_M = 500.0
        const val EXIT_DISTANCE_M = 300.0
        const val STOP_SPEED_KMH = 5.0
        const val STOP_DURATION_MS = 30_000L
        const val GPS_DROPOUT_MS = 10_000L
    }

    var state: ZoneState = ZoneState.Outside
        private set

    private var lastPoint: GpsPoint? = null
    private var activeZone: Zone? = null
    private var entryTime: Long = 0
    private var distanceTraveled: Double = 0.0
    private var effectiveZoneDistance: Double = 0.0
    private var totalStopDurationMs: Long = 0
    private var stopStartTime: Long? = null

    fun update(point: GpsPoint): ZoneState {
        val newState = when (state) {
            is ZoneState.Outside -> handleOutside(point)
            is ZoneState.InZone -> handleInZone(point)
            is ZoneState.Exiting -> handleExiting(point)
        }
        state = newState
        lastPoint = point
        return newState
    }

    fun reset() {
        state = ZoneState.Outside
        lastPoint = null
        activeZone = null
        entryTime = 0
        distanceTraveled = 0.0
        effectiveZoneDistance = 0.0
        totalStopDurationMs = 0
        stopStartTime = null
    }

    private fun handleOutside(point: GpsPoint): ZoneState {
        val zone = RoadMatcher.findMatchingZone(point, zones) ?: return ZoneState.Outside
        val distToStart = RoadMatcher.distanceToZoneStart(point, zone)
        val distToEnd = RoadMatcher.distanceToZoneEnd(point, zone)

        val nearStart = distToStart <= ENTRY_DISTANCE_M
        // Cold-start mid-zone: on the road, heading matches, past the entry buffer,
        // and not already about to exit. Treat as a fresh "joined late" session —
        // average speed is measured over the remaining distance only.
        val midZone = !nearStart && distToEnd > EXIT_DISTANCE_M

        if (!nearStart && !midZone) {
            return ZoneState.Outside
        }

        // Fresh entry anchored to the entry point: full zone if approached from
        // start, remaining great-circle distance to end if joined mid-zone (avg
        // speed is measured from here).
        activeZone = zone
        entryTime = point.timestamp
        distanceTraveled = 0.0
        totalStopDurationMs = 0
        stopStartTime = null
        effectiveZoneDistance = if (nearStart) zone.distanceM.toDouble() else distToEnd

        val status = AverageSpeedCalc.calculate(
            entryTime, point.timestamp, totalStopDurationMs, distanceTraveled,
            effectiveZoneDistance, zone.speedLimits.car,
        )

        return ZoneState.InZone(
            zone = zone,
            entryTime = entryTime,
            distanceTraveled = distanceTraveled,
            avgSpeed = status.avgSpeed,
            speedStatus = status,
            distanceRemaining = polylineRemaining(point, zone),
        )
    }

    private fun handleInZone(point: GpsPoint): ZoneState {
        val zone = activeZone ?: return ZoneState.Outside

        // Accumulate distance via speed × elapsed time (trapezoidal) rather than
        // haversine between consecutive lat/lng. Position estimates may lag the
        // true vehicle position when the Kalman filter is sluggish, which would
        // make distance — and therefore avg — read low. Reported GPS speed is
        // Doppler-derived and tracks the truth far better.
        // Skip on GPS dropout (gap >= GPS_DROPOUT_MS) to avoid phantom distance.
        val prev = lastPoint
        if (prev != null) {
            val gap = point.timestamp - prev.timestamp
            if (gap in 1 until GPS_DROPOUT_MS) {
                val gapSec = gap / 1000.0
                val avgSpeedMs = ((prev.speed + point.speed) / 2.0) / 3.6
                distanceTraveled += avgSpeedMs * gapSec
            }
        }

        // Stop detection
        updateStopTracking(point)

        // Check exit conditions
        if (!RoadMatcher.isOnRoad(point, zone, MAX_ROAD_DISTANCE_M)) {
            return exitZone(point, zone)
        }
        if (RoadMatcher.distanceToZoneEnd(point, zone) < EXIT_DISTANCE_M) {
            return exitZone(point, zone)
        }
        if (distanceTraveled >= zone.distanceM * 1.1) {
            return exitZone(point, zone)
        }

        val status = AverageSpeedCalc.calculate(
            entryTime, point.timestamp, totalStopDurationMs,
            distanceTraveled, effectiveZoneDistance, zone.speedLimits.car,
        )

        return ZoneState.InZone(
            zone = zone,
            entryTime = entryTime,
            distanceTraveled = distanceTraveled,
            avgSpeed = status.avgSpeed,
            speedStatus = status,
            distanceRemaining = polylineRemaining(point, zone),
        )
    }

    private fun handleExiting(point: GpsPoint): ZoneState {
        // Transition to Outside, then try to find a new zone
        resetTrackingState()
        return handleOutside(point)
    }

    private fun exitZone(point: GpsPoint, zone: Zone): ZoneState {
        finalizeStop(point.timestamp)
        val status = AverageSpeedCalc.calculate(
            entryTime, point.timestamp, totalStopDurationMs,
            distanceTraveled, effectiveZoneDistance, zone.speedLimits.car,
        )
        return ZoneState.Exiting(zone = zone, finalAvgSpeed = status.avgSpeed)
    }

    private fun updateStopTracking(point: GpsPoint) {
        if (point.speed < STOP_SPEED_KMH) {
            if (stopStartTime == null) {
                stopStartTime = point.timestamp
            }
        } else {
            finalizeStop(point.timestamp)
        }
    }

    private fun finalizeStop(currentTime: Long) {
        val start = stopStartTime ?: return
        val duration = currentTime - start
        if (duration >= STOP_DURATION_MS) {
            totalStopDurationMs += duration
        }
        stopStartTime = null
    }

    private fun resetTrackingState() {
        activeZone = null
        entryTime = 0
        distanceTraveled = 0.0
        effectiveZoneDistance = 0.0
        totalStopDurationMs = 0
        stopStartTime = null
    }

    // Polyline arc-length from the current GPS position to zone.end. Drives the
    // "X km" label and progress bar — uses the live position rather than the
    // speed×time integrator so it stays accurate across GPS dropouts, mid-zone
    // cold-starts, and simulated jumps.
    private fun polylineRemaining(point: GpsPoint, zone: Zone): Double {
        val traveledOnPolyline = projectOntoPolyline(point.lat, point.lng, zone.centerline)
        return (zone.distanceM.toDouble() - traveledOnPolyline).coerceAtLeast(0.0)
    }
}
