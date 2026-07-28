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
        // Entry provenance. A traversal is only measurable if we watched the
        // vehicle cross the start line, so a confirmed candidate opens a full
        // InZone traversal when its *first* fix projected this close to the
        // start of the centerline, and ZoneState.Unmeasured otherwise. The
        // reason we missed the entry (app restart, permission granted mid-drive,
        // tunnel, process death, genuinely joining the road late) makes no
        // difference to the driver: untrustworthy is untrustworthy, and a
        // partially-informed number is worse than an honest "can't help".
        //
        // Proximity to zone.start cannot make this call — the A3 phantom's first
        // matching fix sat 270–460 m from it, inside the old 500 m entry buffer.
        // Arc position can: for a car genuinely approaching on the road, the
        // first fix that matches the zone at all projects to arc ~0, because a
        // fix short of the camera is still inside the on-road band and its
        // projection clamps to the polyline start.
        //
        // The value is measured, not guessed. Across all 72 bundled zones, the
        // worst first-match arc on a legitimate approach is 121 m at the 2 s
        // near-zone cadence and 148 m at the 5 s cold-start cadence — both at
        // i3-02-north, whose stored centerline opens with a 121 m segment
        // running ~180 degrees against the road (ISSUE-001, shared with
        // i6-01-east and trakiya-03-east), so an approaching car snaps to the
        // far end of that jog rather than to arc 0. 200 m clears the worst
        // legitimate case by 1.35x and still sits under the 268 m the observed
        // A3 phantom projected to. Entry confirmation below remains the primary
        // anti-phantom defence; this constant only separates "approached the
        // camera" from "joined deep inside".
        const val START_WITNESS_ARC_M = 200.0

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

        // Entry confirmation — the mirror of OFF_ROAD_EXIT_GRACE_FIXES on the way
        // in. A fix that merely clips the on-road band must not open a traversal:
        // roads that cross or run alongside a zone sit inside the band, on a
        // course inside DIRECTION_TOLERANCE_DEG, for a few hundred metres. The A3
        // Струма motorway passes within 15 m of the I-1 centerline for ~190 m at
        // the Кочериново interchange, which opened a full phantom traversal of
        // the 10.6 km i1-02-north zone for motorway traffic — reported from a
        // real drive on both platforms (2026-07-26): a 13–21 s "traversal" with
        // an entry announcement and a junk History record.
        //
        // So require the match to hold while the vehicle actually covers this
        // much ground ALONG the centerline before the zone opens. Genuine entries
        // lose nothing: the traversal is back-dated to the candidate's first fix,
        // so only the announcement waits, never the average.
        const val ENTRY_CONFIRM_DISTANCE_M = 300.0
        // …but never more than this share of a zone, so a short zone stays
        // enterable (the shortest in the data is 2.3 km; this only binds below
        // ~1.2 km).
        const val ENTRY_CONFIRM_MAX_FRACTION = 0.25
        // …and over at least this many fixes, so one pair of far-apart fixes
        // (dropout, teleport, coarse simulated trace) can't clear the distance on
        // its own.
        const val ENTRY_CONFIRM_FIXES = 2
        // Drop a half-confirmed candidate that goes quiet for this long — it is
        // no longer evidence of a continuous approach.
        const val ENTRY_CONFIRM_TIMEOUT_MS = 30_000L

        // At a co-located camera pair one camera ends zone A and begins zone B,
        // so B's start sits on A's end (24 such pairs in the data, nearly all
        // exactly 0 m apart). Having just driven A to its end IS the continuous
        // on-road evidence the confirmation window exists to gather, so B skips
        // it — keeping the InZone(A) -> Exiting(A) -> InZone(B) handover (and the
        // chained exit/entry announcement it drives) intact.
        const val COLOCATED_CAMERA_M = 250.0
        // How long the handover stays on offer after the exit. A's exit fires up
        // to EXIT_DISTANCE_M before the shared camera, and B only becomes the
        // *nearest* zone (so the only zone findMatchingZone will return) once we
        // are past it — a few fixes later, not the very next one. The geometric
        // COLOCATED_CAMERA_M test is what actually gates the bypass, so this
        // window can be generous.
        const val COLOCATED_HANDOVER_MS = 30_000L
    }

    /**
     * The offer a just-exited zone leaves behind for a co-located successor: the
     * camera we finished at ([fromZoneEnd]), the direction we were travelling as
     * we finished ([headingDeg], null when the geometry was too short to read a
     * bearing off), and the moment the offer lapses ([expiresAt]).
     *
     * One nullable field rather than three loose ones, so the offer is armed and
     * dropped atomically — a half-cleared handover (an end without its heading)
     * would silently disable the direction guard in [continuesHandoverDirection]
     * and let the opposite-carriageway sibling claim the bypass.
     */
    private class Handover(
        val fromZoneEnd: ZoneEndpoint,
        val headingDeg: Double?,
        val expiresAt: Long,
    )

    /**
     * A zone that matched but has not yet earned a traversal. Accumulates the
     * evidence [ENTRY_CONFIRM_DISTANCE_M] / [ENTRY_CONFIRM_FIXES] ask for, plus
     * the entry-time and distance state to back-date the traversal with once the
     * candidate is confirmed.
     */
    private class PendingEntry(
        val zone: Zone,
        val entryTime: Long,
        val entryArcM: Double,
    ) {
        var fixes: Int = 1
        var lastTime: Long = entryTime
        var lastArcM: Double = entryArcM
        var distanceTraveled: Double = 0.0

        /** Ground covered along the centerline since the candidate opened. */
        val progressM: Double get() = lastArcM - entryArcM

        /**
         * Did we watch this vehicle cross the start line? Decides whether a
         * confirmed candidate graduates into a measured traversal or into
         * [ZoneState.Unmeasured]. See [START_WITNESS_ARC_M].
         */
        val witnessedStart: Boolean get() = entryArcM <= START_WITNESS_ARC_M
    }

    var state: ZoneState = ZoneState.Outside
        private set

    private var lastPoint: GpsPoint? = null
    private var activeZone: Zone? = null
    private var entryTime: Long = 0
    private var distanceTraveled: Double = 0.0
    private var totalStopDurationMs: Long = 0
    private var stopStartTime: Long? = null
    private var offRoadStreak: Int = 0

    // Lifecycle owner: resetTrackingState(). It is the single place that ends a
    // candidate's life for state-machine reasons, and every path that finishes
    // with a zone (handleExiting, leaveUnmeasured) goes through it. handleOutside
    // additionally drops the candidate the moment its evidence stops being
    // evidence — no zone matched, the matched zone is one we are finishing, or it
    // has just graduated into a traversal. Nothing else may clear it.
    private var pendingEntry: PendingEntry? = null

    // Arc length of the previous in-zone fix, used to bridge distance across a
    // GPS dropout (see handleInZone).
    private var lastArcM: Double = 0.0

    // The offer a just-exited zone leaves for a co-located successor, live for
    // COLOCATED_HANDOVER_MS (see the direction guard in handleOutside).
    private var handover: Handover? = null

    fun update(point: GpsPoint, vehicleType: VehicleType = VehicleType.CAR): ZoneState {
        val newState = when (state) {
            is ZoneState.Outside -> handleOutside(point, vehicleType)
            is ZoneState.Unmeasured -> handleUnmeasured(point)
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
        totalStopDurationMs = 0
        stopStartTime = null
        offRoadStreak = 0
        pendingEntry = null
        lastArcM = 0.0
        handover = null
    }

    private fun handleOutside(point: GpsPoint, vehicleType: VehicleType): ZoneState {
        // Past its window the offer is dead — drop it rather than let a later
        // fix find it still sitting there.
        val offer = handover?.takeIf { point.timestamp <= it.expiresAt }
        if (offer == null) handover = null

        val zone = RoadMatcher.findMatchingZone(point, zones)
        if (zone == null) {
            pendingEntry = null
            return ZoneState.Outside
        }
        val arcM = arcLengthOnPolyline(point.lat, point.lng, zone.centerline)
        val remaining = remainingFromArc(zone, arcM)

        // We are finishing this zone, not joining it — never admit it again.
        //
        // Gate on the polyline remainder, not just the straight-line distance to
        // the end: a point just *past* the end that's still within the road-width
        // band (common right after exiting, where the motorway continues straight)
        // has a small distance-to-end but ~0 remaining, and must NOT re-enter the
        // zone we just completed.
        //
        // Also require the point to be more than the exit distance from the end:
        // a centerline that hooks/overshoots at its tail makes two of its legs run
        // within metres of each other near the end, so `arcLengthOnPolyline` can
        // snap a just-exited point back onto the earlier leg and report a large
        // `remaining`. Without this clause that briefly re-admits the zone we are
        // in the middle of exiting (an Exiting -> InZone -> Exiting flap on the
        // final ~100 m; 11/72 zones flapped in qa/validate-zones.sh before it).
        if (remaining <= EXIT_DISTANCE_M ||
            RoadMatcher.distanceToZoneEnd(point, zone) <= EXIT_DISTANCE_M
        ) {
            pendingEntry = null
            return ZoneState.Outside
        }

        // Gather (or extend) the evidence that this is a real entry rather than a
        // neighbouring road clipping the band. A co-located handover already has
        // that evidence — we drove the previous zone to the camera this one
        // starts at — so it opens on the spot.
        val candidate = advancePendingEntry(point, zone, arcM)
        val handedOver = offer != null &&
            haversineDistance(
                offer.fromZoneEnd.lat, offer.fromZoneEnd.lng, zone.start.lat, zone.start.lng,
            ) <= COLOCATED_CAMERA_M &&
            continuesHandoverDirection(offer, zone)
        if (!handedOver && !isConfirmed(candidate, zone)) {
            return ZoneState.Outside
        }

        // Confirmed — but confirmation only proves we have been on this road, not
        // that we saw the driver pass the entry camera. A co-located handover is
        // witnessed by construction: driving the previous zone to its end *is*
        // crossing this one's start camera, whatever arc the first fix on the new
        // zone happened to land at.
        pendingEntry = null
        handover = null
        activeZone = zone
        totalStopDurationMs = 0
        stopStartTime = null
        offRoadStreak = 0
        lastArcM = arcM

        if (!candidate.witnessedStart && !handedOver) {
            // We are demonstrably inside the zone but never saw the entry, so
            // there is nothing trustworthy to measure. Show the road's facts and
            // stay quiet — see ZoneState.Unmeasured.
            entryTime = 0
            distanceTraveled = 0.0
            return ZoneState.Unmeasured(zone = zone, distanceRemaining = remaining)
        }

        // Open the traversal back-dated to the candidate's *first* fix — its
        // timestamp and the ground covered since — so the confirmation window
        // costs announcement latency, never averaging accuracy. The averaging
        // denominator is always the whole zone: a tracked traversal is by
        // definition one we watched from the start. Use the polyline remainder —
        // not the straight-line distance to the end — so the legal-time budget
        // matches the road actually left to drive.
        entryTime = candidate.entryTime
        distanceTraveled = candidate.distanceTraveled

        val status = AverageSpeedCalc.calculate(
            entryTime, point.timestamp, totalStopDurationMs, distanceTraveled,
            zone.distanceM.toDouble(), vehicleType.limit(zone.speedLimits),
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

    private fun handleInZone(point: GpsPoint, vehicleType: VehicleType): ZoneState {
        val zone = activeZone ?: return ZoneState.Outside

        // One walk of the centerline serves the distance integrator, the off-road
        // test and the remaining label below.
        val position = positionOnPolyline(point.lat, point.lng, zone.centerline)
        val arcM = position?.arcLengthM ?: lastArcM
        val centerlineDist = position?.distanceFromLineM ?: Double.MAX_VALUE

        distanceTraveled += travelSince(lastPoint, point, lastArcM, arcM)
        lastArcM = arcM

        // Stop detection
        updateStopTracking(point)

        // Accurate live distance to the zone end from the polyline projection —
        // drift-free, unlike the speed×time integrator above. Drives the exit
        // decision, the user-facing remaining label, and the remainder-speed math
        // so integrator drift (or unevenly-spaced simulated fixes) can't fake an
        // early "overshot the end" exit or collapse the remainder to 0 mid-zone.
        val remaining = remainingFromArc(zone, arcM)

        // Check exit conditions. Use the zone-appropriate on-road band (the
        // motorway override widens it to 150 m) — the same band entry matching
        // uses — so a motorway bend doesn't read off-road in-zone yet on-road for
        // entry. A single off-road fix is treated as a transient blip: only exit
        // once it persists OFF_ROAD_EXIT_GRACE_FIXES fixes, or immediately when the
        // fix is OFF_ROAD_HARD_M past the road (a real departure, not a blip).
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
            distanceTraveled, zone.distanceM.toDouble(), vehicleType.limit(zone.speedLimits),
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

    /**
     * Inside a zone we never saw entered. The only job here is to notice when we
     * leave it — deliberately no distance integration, no stop tracking, no
     * [AverageSpeedCalc]: there is no measurement to keep, so there is nothing to
     * accidentally surface.
     *
     * Every departure lands on [ZoneState.Outside] rather than
     * [ZoneState.Exiting], because there is no traversal to finalize. That is
     * what keeps a mid-zone join out of History and out of the exit
     * announcement, with no suppression logic needed at the consumer layers.
     */
    private fun handleUnmeasured(point: GpsPoint): ZoneState {
        val zone = activeZone ?: return ZoneState.Outside

        val position = positionOnPolyline(point.lat, point.lng, zone.centerline)
        val arcM = position?.arcLengthM ?: lastArcM
        val centerlineDist = position?.distanceFromLineM ?: Double.MAX_VALUE
        lastArcM = arcM

        // Same off-road hysteresis as handleInZone: a single wide fix is usually
        // a Kalman lag on a bend or a momentary glitch, not a departure.
        if (centerlineDist > RoadMatcher.maxOnRoadDistanceM(zone)) {
            offRoadStreak++
            val farGone = centerlineDist > OFF_ROAD_HARD_M
            if (farGone || offRoadStreak >= OFF_ROAD_EXIT_GRACE_FIXES) {
                return leaveUnmeasured()
            }
        } else {
            offRoadStreak = 0
        }

        val remaining = remainingFromArc(zone, arcM)
        if (RoadMatcher.distanceToZoneEnd(point, zone) < EXIT_DISTANCE_M || remaining <= 0.0) {
            return leaveUnmeasured()
        }

        return ZoneState.Unmeasured(zone = zone, distanceRemaining = remaining)
    }

    // Leaving an Unmeasured zone is not an exit — nothing was being measured, so
    // there is no traversal to finalize and no co-located handover to arm (a
    // successor zone earns its own entry the normal way). The next fix runs
    // through handleOutside, exactly as it does one fix after an Exiting.
    private fun leaveUnmeasured(): ZoneState {
        resetTrackingState()
        return ZoneState.Outside
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
            distanceTraveled, zone.distanceM.toDouble(), vehicleType.limit(zone.speedLimits),
        )
        // Offer a co-located successor the handover (see COLOCATED_CAMERA_M),
        // tagged with the direction we finished this zone on so the opposite
        // carriageway can't claim it (see continuesHandoverDirection).
        //
        // pendingEntry is deliberately NOT cleared here — resetTrackingState()
        // owns that, and handleExiting calls it before the next handleOutside.
        handover = Handover(
            fromZoneEnd = zone.end,
            headingDeg = localPolylineBearing(
                zone.centerline,
                polylineLengthByZoneId[zone.id] ?: polylineLengthMeters(zone.centerline),
                RoadMatcher.LOCAL_BEARING_WINDOW_M,
            ),
            expiresAt = point.timestamp + COLOCATED_HANDOVER_MS,
        )
        return ZoneState.Exiting(zone = zone, finalAvgSpeed = status.avgSpeed)
    }

    /**
     * Ground covered between [prev] and [point], for the distance integrator.
     *
     * Normally speed × elapsed time (trapezoidal) rather than the haversine
     * between consecutive lat/lng: position estimates lag the true vehicle
     * position when the Kalman filter is sluggish, which would make distance —
     * and therefore avg — read low, while reported GPS speed is Doppler-derived
     * and tracks the truth far better.
     *
     * Across a GPS dropout (gap >= [GPS_DROPOUT_MS]) there are no samples to
     * integrate, so fall back to how far the projection onto the centerline
     * moved — from [prevArcM] to [arcM] — because the car demonstrably covered
     * that ground. Dropping the gap outright (the old behaviour) left `elapsed`
     * counting time the numerator never got credit for, deflating the reported
     * average: a ~15 s dropout turned an ~87 km/h drive into a reported 24 km/h
     * (real drive, 2026-07-26).
     *
     * Two integrators call this with the same [prev] but a different arc
     * baseline: the active traversal passes [lastArcM], the pending-entry buffer
     * passes its candidate's own `lastArcM`. That works only because both walk
     * the *same* fix stream — [lastPoint] is always the fix immediately before
     * [point] for either of them — so pass the baseline in explicitly rather
     * than reading a field, and the coupling stays visible at the call site.
     */
    private fun travelSince(
        prev: GpsPoint?,
        point: GpsPoint,
        prevArcM: Double,
        arcM: Double,
    ): Double {
        if (prev == null) return 0.0
        val gap = point.timestamp - prev.timestamp
        return when {
            gap in 1 until GPS_DROPOUT_MS -> ((prev.speed + point.speed) / 2.0 / 3.6) * (gap / 1000.0)
            gap >= GPS_DROPOUT_MS -> (arcM - prevArcM).coerceAtLeast(0.0)
            else -> 0.0
        }
    }

    /**
     * Open or extend the candidate entry for [zone], returning the live
     * candidate. Restarts from this fix whenever the previous candidate was for
     * a different zone, or went quiet past [ENTRY_CONFIRM_TIMEOUT_MS] — in both
     * cases the earlier evidence no longer describes a continuous approach.
     */
    private fun advancePendingEntry(
        point: GpsPoint,
        zone: Zone,
        arcM: Double,
    ): PendingEntry {
        val open = pendingEntry
        val continues = open != null &&
            open.zone.id == zone.id &&
            point.timestamp - open.lastTime <= ENTRY_CONFIRM_TIMEOUT_MS
        val candidate = if (continues) {
            checkNotNull(open).also {
                it.fixes++
                it.distanceTraveled += travelSince(lastPoint, point, it.lastArcM, arcM)
                it.lastArcM = arcM
                it.lastTime = point.timestamp
            }
        } else {
            PendingEntry(
                zone = zone,
                entryTime = point.timestamp,
                entryArcM = arcM,
            )
        }
        pendingEntry = candidate
        return candidate
    }

    /**
     * Does [zone] continue the direction we were travelling when [offer] was
     * made? The proximity test alone is not enough: at a co-located
     * camera the **opposite-carriageway sibling** also starts within
     * [COLOCATED_CAMERA_M] — trakiya-03-west's start is 15 m from
     * trakiya-03-east's end, which is also trakiya-04-east's start — so without
     * this it can claim the bypass and open a *measured* traversal of the zone
     * running back the way we came, on a single wrong-bearing fix. That is
     * exactly what a stored centerline with an ISSUE-001 backwards start jog
     * produces: `trakiya-04-east` opens with a 19 m segment bearing west, so one
     * fix at the seam legitimately reads as westbound. Caught by
     * `qa/colocated-zones.sh --all` (7/24 pairs).
     *
     * Compare the heading we finished the previous zone on against this zone's
     * local heading at its start — the same ±[RoadMatcher.LOCAL_BEARING_WINDOW_M]
     * window `RoadMatcher` uses, so a start jog is averaged out rather than read
     * literally.
     */
    private fun continuesHandoverDirection(offer: Handover, zone: Zone): Boolean {
        val fromHeading = offer.headingDeg ?: return true
        val startHeading = localPolylineBearing(
            zone.centerline, 0.0, RoadMatcher.LOCAL_BEARING_WINDOW_M,
        ) ?: return true
        return bearingDifference(fromHeading, startHeading) <= RoadMatcher.DIRECTION_TOLERANCE_DEG
    }

    /** Has [candidate] earned a traversal? See [ENTRY_CONFIRM_DISTANCE_M]. */
    private fun isConfirmed(candidate: PendingEntry, zone: Zone): Boolean {
        val required = minOf(
            ENTRY_CONFIRM_DISTANCE_M,
            zone.distanceM.toDouble() * ENTRY_CONFIRM_MAX_FRACTION,
        )
        return candidate.fixes >= ENTRY_CONFIRM_FIXES && candidate.progressM >= required
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

    // NB: deliberately does NOT clear `handover` — handleExiting calls this on
    // its way into handleOutside, which is exactly where the co-located handover
    // has to survive to be seen. That inversion is safe because the offer is
    // self-expiring (Handover.expiresAt, checked and dropped at the top of
    // handleOutside), so a stale one cannot outlive COLOCATED_HANDOVER_MS even
    // if a future caller resets tracking without exiting a zone. Arming it stays
    // the exclusive business of exitZone().
    private fun resetTrackingState() {
        activeZone = null
        entryTime = 0
        distanceTraveled = 0.0
        totalStopDurationMs = 0
        stopStartTime = null
        offRoadStreak = 0
        lastArcM = 0.0
        pendingEntry = null
    }

    // Remaining road to the end for a point already projected onto the
    // centerline. Measured along the centerline geometry itself (its arc
    // length), not the official zone.distanceM: the scraper aligns the
    // centerline so the two match for shipped data, but deriving from the
    // geometry keeps "remaining" exactly 0 at the polyline end regardless, so
    // the "past the end" checks (mid-zone re-entry guard, end-of-zone exit) stay
    // correct even if distanceM and the centerline ever disagree.
    //
    // Position-derived rather than integrator-derived, so it stays accurate
    // across GPS dropouts, mid-zone cold-starts, and simulated jumps.
    private fun remainingFromArc(zone: Zone, arcM: Double): Double {
        val totalLength = polylineLengthByZoneId[zone.id] ?: polylineLengthMeters(zone.centerline)
        return (totalLength - arcM).coerceAtLeast(0.0)
    }
}
