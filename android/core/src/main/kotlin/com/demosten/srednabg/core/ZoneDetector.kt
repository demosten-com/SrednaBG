// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

/**
 * Stateful zone-tracking state machine. Holds mutable state ([state]) across
 * [update] calls and performs no internal synchronization — it is **not**
 * thread-safe and must be confined to a single thread. In the app that thread is
 * the `LocationTrackingService` GPS-consumer coroutine, which owns the only
 * instance. (The Swift port documents the same contract as a mutating value type
 * embedded inside a `@MainActor` class.)
 */
class ZoneDetector(zones: List<Zone>) {

    // Orient every zone's centerline to run start → end once, up front, so all the
    // order-dependent geometry below (direction matching, polyline projection,
    // remaining distance, puck snapping) is correct regardless of how the source
    // stored the points. A centerline stored end-first — a real server-data bug
    // (the scraper aligns the bundle, but the live /api/zones may still serve it
    // and the device syncs that into Room) — would otherwise flip a zone's
    // apparent direction, so the app matches the opposite-carriageway sibling and
    // reports an inverted "remaining" (observed live via `qa/feed-zone.sh 0` on
    // europa-01-north). The start/end endpoints are authoritative, so orienting to
    // them makes the engine immune to the bad point order. See
    // orientCenterlineToStart + ZoneDetectorTest reversed-centerline cases.
    private val zones: List<Zone> = zones.map { zone ->
        zone.copy(centerline = orientCenterlineToStart(zone.centerline, zone.start))
    }

    // A zone's centerline is immutable after the orientation above, so its total
    // arc length never changes — cache it per zone id rather than re-summing the
    // haversines on every 1 Hz fix in polylineRemaining().
    private val polylineLengthByZoneId: Map<String, Double> =
        this.zones.associate { it.id to polylineLengthMeters(it.centerline) }

    companion object {
        const val ENTRY_DISTANCE_M = 500.0
        // Declare the zone finished once within this straight-line distance of the
        // end — by here the end camera is in sight, but the average + remainder
        // guidance stayed live through almost the whole zone. Relies on the
        // centerline actually reaching zone.end (the scraper aligns it), so this
        // trips cleanly near the real end rather than hundreds of metres short.
        const val EXIT_DISTANCE_M = 100.0
        const val STOP_SPEED_KMH = 5.0
        const val STOP_DURATION_MS = 30_000L
        const val GPS_DROPOUT_MS = 10_000L

        // Off-road exit hysteresis. A single off-road fix is usually a transient
        // GPS/Kalman blip — the smoothed position lags the road on a bend (worse
        // on coarsely-sampled centerlines), or a momentary glitch (overpass,
        // tunnel mouth, urban canyon) throws one fix wide. Exiting on the first
        // such fix produces a spurious Exiting -> InZone flap. So require the
        // off-road condition to persist this many consecutive fixes before we
        // declare an exit; a genuine off-ramp diverges steadily and trips it
        // within a few seconds. Caught by qa/validate-zones.sh (struma-02-north /
        // trakiya-01-west / hemus-02-west flapped on coarser server centerlines).
        const val OFF_ROAD_EXIT_GRACE_FIXES = 3
        // …unless the fix is this far off the centerline, which is no blip but a
        // real departure (different road / GPS teleport) — exit immediately.
        const val OFF_ROAD_HARD_M = 1000.0
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
    private var offRoadStreak: Int = 0

    fun update(point: GpsPoint, vehicleType: VehicleType = VehicleType.CAR): ZoneState {
        val newState = when (state) {
            is ZoneState.Outside -> handleOutside(point, vehicleType)
            is ZoneState.InZone -> handleInZone(point, vehicleType)
            is ZoneState.Exiting -> handleExiting(point, vehicleType)
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
        offRoadStreak = 0
    }

    private fun handleOutside(point: GpsPoint, vehicleType: VehicleType): ZoneState {
        val zone = RoadMatcher.findMatchingZone(point, zones) ?: return ZoneState.Outside
        val distToStart = RoadMatcher.distanceToZoneStart(point, zone)
        val remaining = polylineRemaining(point, zone)

        val nearStart = distToStart <= ENTRY_DISTANCE_M
        // Cold-start mid-zone: on the road, heading matches, past the entry buffer,
        // with meaningful road still ahead. Treat as a fresh "joined late" session
        // — average speed is measured over the remaining distance only.
        //
        // Gate on the polyline remainder, not the straight-line distance to the
        // end: a point just *past* the end that's still within the road-width band
        // (common right after exiting, where the motorway continues straight)
        // has a small distToEnd-equivalent but ~0 remaining, and must NOT re-enter
        // the zone we just completed.
        //
        // Also require the point to be more than the exit distance from the end:
        // a centerline that hooks/overshoots at its tail makes two of its legs run
        // within metres of each other near the end, so `arcLengthOnPolyline` can
        // snap a just-exited point back onto the earlier leg and report a large
        // `remaining`. Without this clause that briefly re-admits the zone we are
        // in the middle of exiting (Exiting -> InZone -> Exiting flap on the final
        // ~100 m). We are finishing the zone here, not joining it late.
        val midZone = !nearStart && remaining > EXIT_DISTANCE_M &&
            RoadMatcher.distanceToZoneEnd(point, zone) > EXIT_DISTANCE_M

        if (!nearStart && !midZone) {
            return ZoneState.Outside
        }

        // Fresh entry anchored to the entry point: full zone if approached from
        // start, remaining polyline arc-length to end if joined mid-zone (avg
        // speed is measured from here). Use the polyline remainder — not the
        // straight-line distToEnd — so the legal-time budget below matches the
        // road actually left to drive.
        activeZone = zone
        entryTime = point.timestamp
        distanceTraveled = 0.0
        totalStopDurationMs = 0
        stopStartTime = null
        offRoadStreak = 0
        effectiveZoneDistance = if (nearStart) zone.distanceM.toDouble() else remaining

        val status = AverageSpeedCalc.calculate(
            entryTime, point.timestamp, totalStopDurationMs, distanceTraveled,
            effectiveZoneDistance, vehicleType.limit(zone.speedLimits),
        )

        return ZoneState.InZone(
            zone = zone,
            entryTime = entryTime,
            distanceTraveled = distanceTraveled,
            speedStatus = status,
            distanceRemaining = remaining,
        )
    }

    private fun handleInZone(point: GpsPoint, vehicleType: VehicleType): ZoneState {
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

        // Accurate live distance to the zone end from the polyline projection —
        // drift-free, unlike the speed×time integrator above. Drives the exit
        // decision, the user-facing remaining label, and the remainder-speed math
        // so integrator drift (or unevenly-spaced simulated fixes) can't fake an
        // early "overshot the end" exit or collapse the remainder to 0 mid-zone.
        val remaining = polylineRemaining(point, zone)

        // Check exit conditions. Use the zone-appropriate on-road band (the
        // motorway override widens it to 150 m) — the same band entry matching
        // uses — so a motorway bend doesn't read off-road in-zone yet on-road for
        // entry. A single off-road fix is treated as a transient blip: only exit
        // once it persists OFF_ROAD_EXIT_GRACE_FIXES fixes, or immediately when the
        // fix is OFF_ROAD_HARD_M past the road (a real departure, not a blip).
        val centerlineDist = RoadMatcher.distanceToCenterline(point, zone)
        if (centerlineDist > RoadMatcher.maxOnRoadDistanceM(zone)) {
            offRoadStreak++
            val farGone = centerlineDist > OFF_ROAD_HARD_M
            if (farGone || offRoadStreak >= OFF_ROAD_EXIT_GRACE_FIXES) {
                return exitZone(point, zone, vehicleType)
            }
            // Within the grace window — stay in the zone and keep guidance live.
        } else {
            offRoadStreak = 0
        }
        if (RoadMatcher.distanceToZoneEnd(point, zone) < EXIT_DISTANCE_M) {
            return exitZone(point, zone, vehicleType)
        }
        // Reached the polyline end (e.g. zone end point offset from the road so
        // the haversine check above never trips). Position-based backstop,
        // replacing the old `distanceTraveled >= distanceM * 1.1` integrator
        // check that drifted on simulated/noisy traces.
        if (remaining <= 0.0) {
            return exitZone(point, zone, vehicleType)
        }

        val status = AverageSpeedCalc.calculate(
            entryTime, point.timestamp, totalStopDurationMs,
            distanceTraveled, effectiveZoneDistance, vehicleType.limit(zone.speedLimits),
            distanceRemainingOverride = remaining,
        )

        return ZoneState.InZone(
            zone = zone,
            entryTime = entryTime,
            distanceTraveled = distanceTraveled,
            speedStatus = status,
            distanceRemaining = remaining,
        )
    }

    private fun handleExiting(point: GpsPoint, vehicleType: VehicleType): ZoneState {
        // Transition to Outside, then try to find a new zone
        resetTrackingState()
        return handleOutside(point, vehicleType)
    }

    private fun exitZone(point: GpsPoint, zone: Zone, vehicleType: VehicleType): ZoneState {
        finalizeStop(point.timestamp)
        val status = AverageSpeedCalc.calculate(
            entryTime, point.timestamp, totalStopDurationMs,
            distanceTraveled, effectiveZoneDistance, vehicleType.limit(zone.speedLimits),
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
        offRoadStreak = 0
    }

    // Polyline arc-length from the current GPS position to zone.end. Drives the
    // "X km" label and progress bar — uses the live position rather than the
    // speed×time integrator so it stays accurate across GPS dropouts, mid-zone
    // cold-starts, and simulated jumps.
    // Remaining road to the end, measured along the centerline geometry itself
    // (its arc length), not the official zone.distanceM. The scraper aligns the
    // centerline so the two match for shipped data; deriving from the geometry
    // here keeps "remaining" exactly 0 at the polyline end regardless, so the
    // "past the end" checks (mid-zone re-entry guard, end-of-zone exit) stay
    // correct even if distanceM and the centerline ever disagree.
    private fun polylineRemaining(point: GpsPoint, zone: Zone): Double {
        val traveledOnPolyline = arcLengthOnPolyline(point.lat, point.lng, zone.centerline)
        val totalLength = polylineLengthByZoneId[zone.id] ?: polylineLengthMeters(zone.centerline)
        return (totalLength - traveledOnPolyline).coerceAtLeast(0.0)
    }
}
