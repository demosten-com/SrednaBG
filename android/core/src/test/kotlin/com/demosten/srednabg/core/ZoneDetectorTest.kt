// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

class ZoneDetectorTest {

    private lateinit var detector: ZoneDetector

    @BeforeEach
    fun setUp() {
        detector = ZoneDetector(listOf(TRAKIYA_T10, HEMUS_H12, I4_10))
    }

    @Test
    fun `full traversal at legal speed`() {
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 130.0)
        assertTrue(trace.size > 10, "Trace should have many points")

        var sawOutside = false
        var sawInZone = false
        var sawExiting = false
        var sawUnmeasured = false

        for (point in trace) {
            val state = detector.update(point)
            when (state) {
                is ZoneState.Outside -> sawOutside = true
                is ZoneState.Unmeasured -> sawUnmeasured = true
                is ZoneState.InZone -> {
                    sawInZone = true
                    assertFalse(state.speedStatus.isOverLimit, "Should not be over limit at 130 km/h")
                }
                is ZoneState.Exiting -> {
                    sawExiting = true
                    // Final avg speed should be approximately 130 km/h
                    // (with tolerance for centerline interpolation)
                    val avg = state.finalAvgSpeed!!
                    assertTrue(avg > 100, "Final speed $avg too low")
                    assertTrue(avg < 180, "Final speed $avg too high")
                }
            }
        }

        assertTrue(sawOutside, "Should have been Outside initially")
        assertTrue(sawInZone, "Should have been InZone during traversal")
        assertTrue(sawExiting, "Should have Exiting state")
        assertFalse(
            sawUnmeasured,
            "A trace that approaches from before the entry camera is a witnessed " +
                "entry — it must never degrade to Unmeasured",
        )
    }

    @Test
    fun `full traversal while speeding`() {
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 160.0)

        var lastInZone: ZoneState.InZone? = null
        for (point in trace) {
            val state = detector.update(point)
            if (state is ZoneState.InZone) {
                lastInZone = state
            }
        }

        assertFalse(lastInZone == null, "Should have been in zone")
        // After driving at 160 in a 140 zone, should be over limit
        assertTrue(lastInZone!!.speedStatus.isOverLimit, "Should be over limit at 160 km/h")
    }

    @Test
    fun `stop detection excludes long stop`() {
        val trace = generateTraceWithStop(
            TRAKIYA_T10,
            speedKmh = 130.0,
            stopDurationMs = 120_000L, // 2-minute stop
        )

        var exitState: ZoneState.Exiting? = null
        for (point in trace) {
            val state = detector.update(point)
            if (state is ZoneState.Exiting) {
                exitState = state
            }
        }

        assertFalse(exitState == null, "Should have exited zone")
        // With stop excluded, avg speed should reflect driving speed (~130), not
        // the diluted average that includes stop time
        assertTrue(exitState!!.finalAvgSpeed!! > 80, "Avg speed ${exitState.finalAvgSpeed} too low (stop not excluded?)")
    }

    @Test
    fun `brief stop under 30s is NOT excluded`() {
        val trace = generateTraceWithStop(
            TRAKIYA_T10,
            speedKmh = 130.0,
            stopDurationMs = 20_000L, // 20-second stop (under threshold)
        )

        var exitState: ZoneState.Exiting? = null
        for (point in trace) {
            val state = detector.update(point)
            if (state is ZoneState.Exiting) {
                exitState = state
            }
        }

        assertFalse(exitState == null, "Should have exited zone")
        // Brief stop dilutes the average — avg should be lower than 130
        // because the 20s counts against active time
        assertTrue(exitState!!.finalAvgSpeed!! < 130,
            "Brief stop should count against driver, but avg=${exitState.finalAvgSpeed}")
    }

    @Test
    fun `gps dropout does not add phantom distance`() {
        val traceNormal = generateGpsTrace(TRAKIYA_T10, speedKmh = 130.0)
        val traceDropout = generateTraceWithDropout(
            TRAKIYA_T10,
            speedKmh = 130.0,
            dropoutDurationMs = 15_000L,
        )

        // Run both through separate detectors
        val detectorNormal = ZoneDetector(listOf(TRAKIYA_T10))
        val detectorDropout = ZoneDetector(listOf(TRAKIYA_T10))

        var normalMaxDist = 0.0
        var dropoutMaxDist = 0.0

        for (point in traceNormal) {
            val state = detectorNormal.update(point)
            if (state is ZoneState.InZone) {
                normalMaxDist = maxOf(normalMaxDist, state.distanceTraveled)
            }
        }

        for (point in traceDropout) {
            val state = detectorDropout.update(point)
            if (state is ZoneState.InZone) {
                dropoutMaxDist = maxOf(dropoutMaxDist, state.distanceTraveled)
            }
        }

        // Dropout trace should accumulate LESS distance (the gap segment is skipped)
        assertTrue(dropoutMaxDist < normalMaxDist,
            "Dropout should have less distance: $dropoutMaxDist vs $normalMaxDist")
    }

    @Test
    fun `cold-start mid-zone is Unmeasured, never a measured traversal`() {
        // Simulates opening the app while already deep inside a zone. We never saw
        // the entry camera, so there is nothing trustworthy to average: a running
        // average over the remainder alone matches nothing BG TOLL computes, yet
        // used to be rendered in the same chip, spoken in the same phrase and
        // stored in the same History row as a real traversal (the junk 24 km/h
        // record, real drive 2026-07-26). The reason we missed the entry is
        // deliberately irrelevant — see ZoneDetector.START_WITNESS_ARC_M.
        val midArc = arcLengthOnPolyline(42.510, 23.770, TRAKIYA_T10.centerline)
        val states = collectAlongCenterline(
            detector,
            TRAKIYA_T10,
            fromArcM = midArc,
            metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 2,
        )
        assertTrue(
            states.none { it is ZoneState.InZone },
            "A mid-zone cold start must never open a measured traversal",
        )
        val state = states.last()
        assertTrue(state is ZoneState.Unmeasured, "Should be Unmeasured mid-zone, got $state")
        val unmeasured = state as ZoneState.Unmeasured
        assertEquals(TRAKIYA_T10.id, unmeasured.zone.id)
        // distanceRemaining is polyline arc-length to zone.end — a fact about the
        // road, true regardless of when we joined, so it is one of the two things
        // this state may show (with the zone's speed limit).
        assertTrue(unmeasured.distanceRemaining < TRAKIYA_T10.distanceM,
            "Polyline-remaining ${unmeasured.distanceRemaining} should be less than " +
                "full zone ${TRAKIYA_T10.distanceM}")
        assertTrue(unmeasured.distanceRemaining > 1000,
            "Mid-zone join should still have meaningful distance remaining " +
                "(${unmeasured.distanceRemaining})")
    }

    @Test
    fun `distanceRemaining tracks live polyline projection, not speed-time integrator`() {
        // Regression for QA screenshot bug: progress bar / km label drifted off the
        // real position because they were derived from speed×time accumulation
        // (distanceTraveled), which lags or jumps under simulated traces and GPS
        // dropouts. The fix sources distanceRemaining from projectOntoPolyline so
        // it matches the live GPS dot regardless of integrator state.
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val bearing = polylineBearing(TRAKIYA_T10.centerline)

        // Drive a few normal points near the start to enter and put the integrator
        // at a small distanceTraveled.
        for (i in 0..4) {
            val frac = i / 100.0
            val lat = TRAKIYA_T10.start.lat + (TRAKIYA_T10.end.lat - TRAKIYA_T10.start.lat) * frac
            val lng = TRAKIYA_T10.start.lng + (TRAKIYA_T10.end.lng - TRAKIYA_T10.start.lng) * frac
            det.update(GpsPoint(lat, lng, 130.0, EPOCH_BASE + i * 1000L, bearing))
        }

        // Now jump the GPS to the second-to-last centerline vertex (≈80%+ along
        // the polyline). The integrator hasn't caught up — but the user-facing
        // distanceRemaining must reflect the live position.
        val nearEndVertex = TRAKIYA_T10.centerline[TRAKIYA_T10.centerline.size - 2]
        val nearEnd = GpsPoint(
            lat = nearEndVertex[0], lng = nearEndVertex[1],
            speed = 130.0, timestamp = EPOCH_BASE + 10_000L, bearing = bearing,
        )
        val state = det.update(nearEnd) as ZoneState.InZone

        // Position is past 80% of the polyline, so remaining must be a small
        // fraction of the full zone length — far less than the integrator-derived
        // ~9 km that would surface from speed×time over only 10 seconds.
        val remainingFraction = state.distanceRemaining / TRAKIYA_T10.distanceM.toDouble()
        assertTrue(remainingFraction < 0.25,
            "Near-end projection should leave <25% remaining, got ${remainingFraction * 100}%")
    }

    @Test
    fun `cold-start very near zone end stays Outside`() {
        // Within EXIT_DISTANCE_M (300m) of zone end — not worth entering
        val bearing = polylineBearing(TRAKIYA_T10.centerline)
        val nearEnd = GpsPoint(
            lat = TRAKIYA_T10.end.lat,
            lng = TRAKIYA_T10.end.lng,
            speed = 130.0,
            timestamp = EPOCH_BASE,
            bearing = bearing,
        )

        val state = detector.update(nearEnd)
        assertEquals(ZoneState.Outside, state,
            "Should not enter zone when already at the exit endpoint")
    }

    @Test
    fun `exit on leaving road`() {
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 130.0)

        // Feed enough points to clear the entry-confirmation window and enter.
        var enteredZone = false
        for (point in trace.take(25)) {
            val state = detector.update(point)
            if (state is ZoneState.InZone) {
                enteredZone = true
                break
            }
        }
        assertTrue(enteredZone, "Should have entered zone")

        // Now send a point far from the centerline (off-ramp)
        val offRoadPoint = GpsPoint(
            lat = 42.6, lng = 23.9, speed = 80.0,
            timestamp = EPOCH_BASE + 20_000,
            bearing = 180.0,
        )
        val state = detector.update(offRoadPoint)
        assertTrue(state is ZoneState.Exiting, "Should exit when leaving road")
    }

    @Test
    fun `transient off-road blip does not exit, but sustained off-road does`() {
        // Regression for the qa/validate-zones flap on motorway zones
        // (struma-02-north / trakiya-01-west / hemus-02-west on the coarser server
        // centerlines): the Kalman-smoothed position lags off the road for a fix or
        // two on a bend, which used to trigger an immediate Exiting -> InZone flap.
        // A single off-road fix must now be absorbed; only a sustained departure
        // exits.
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 130.0)
        val det = ZoneDetector(listOf(TRAKIYA_T10))

        var lastInZone: GpsPoint? = null
        for (point in trace) {
            if (det.update(point) is ZoneState.InZone) lastInZone = point
            if (lastInZone != null) break
        }
        assertTrue(lastInZone != null, "Should have entered the zone")

        // ~220 m perpendicular off the centerline — past the 150 m motorway band
        // but well within OFF_ROAD_HARD_M, i.e. a blip, not a departure.
        val base = lastInZone!!
        fun offRoad(seq: Int) = GpsPoint(
            lat = base.lat + 0.003, lng = base.lng, speed = 130.0,
            timestamp = base.timestamp + seq * 1000, bearing = base.bearing,
        )

        assertTrue(det.update(offRoad(1)) is ZoneState.InZone, "1st off-road fix must be absorbed")
        assertTrue(det.update(offRoad(2)) is ZoneState.InZone, "2nd off-road fix must be absorbed")
        assertTrue(
            det.update(offRoad(3)) is ZoneState.Exiting,
            "Sustained off-road (>= OFF_ROAD_EXIT_GRACE_FIXES) must exit",
        )
    }

    @Test
    fun `back on-road within the grace window keeps the same traversal`() {
        // A blip that recovers before the grace elapses must not have exited at all
        // — same uninterrupted traversal (entryTime unchanged).
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 130.0)
        val det = ZoneDetector(listOf(TRAKIYA_T10))

        var entryTime: Long? = null
        var idx = 0
        while (idx < trace.size) {
            val s = det.update(trace[idx]); idx++
            if (s is ZoneState.InZone) { entryTime = s.entryTime; break }
        }
        assertTrue(entryTime != null, "Should have entered the zone")

        // Two off-road fixes (under the grace), then back on the planned route.
        val onResume = trace[idx]
        det.update(onResume.copy(lat = onResume.lat + 0.003, timestamp = onResume.timestamp))
        det.update(onResume.copy(lat = onResume.lat + 0.003, timestamp = onResume.timestamp + 1000))
        val resumed = det.update(onResume.copy(timestamp = onResume.timestamp + 2000))

        assertTrue(resumed is ZoneState.InZone, "Should still be in the zone after the blip")
        assertEquals(
            entryTime, (resumed as ZoneState.InZone).entryTime,
            "Blip must not have restarted the traversal",
        )
    }

    @Test
    fun `reset clears state`() {
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 130.0)

        // Enter the zone
        for (point in trace.take(10)) {
            detector.update(point)
        }

        detector.reset()
        assertEquals(ZoneState.Outside, detector.state, "Reset should return to Outside")
    }

    @Test
    fun `exiting transitions to outside on next update`() {
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 130.0)

        var exitingIdx = -1
        for ((idx, point) in trace.withIndex()) {
            val state = detector.update(point)
            if (state is ZoneState.Exiting) {
                exitingIdx = idx
                break
            }
        }
        assertTrue(exitingIdx > 0, "Should have reached Exiting state")

        // Next update should be Outside (or new zone entry)
        if (exitingIdx + 1 < trace.size) {
            val state = detector.update(trace[exitingIdx + 1])
            assertTrue(state is ZoneState.Outside || state is ZoneState.InZone,
                "After Exiting, should be Outside or in new zone")
        }
    }

    @Test
    fun `opposite direction does not match zone`() {
        // Generate trace along Trakiya but use opposite direction zone in detector
        val detectorOpposite = ZoneDetector(listOf(TRAKIYA_T10))
        val trace = generateGpsTrace(TRAKIYA_T10_OPPOSITE, speedKmh = 130.0)

        var sawInZone = false
        for (point in trace) {
            val state = detectorOpposite.update(point)
            if (state is ZoneState.InZone) {
                sawInZone = true
            }
        }

        // Driving east should not match a west-direction zone
        assertFalse(sawInZone, "Opposite direction should not enter zone")
    }

    @Test
    fun `re-joining mid-zone after an off-road exit is Unmeasured, not a second traversal`() {
        // Drive into the zone through its entry camera, leave the road (which
        // finalizes that traversal), then rejoin the road 30 % in.
        //
        // The rejoin does not cross the entry camera, so it cannot be measured:
        // it used to open a *second* traversal whose average covered only the
        // remainder, producing a junk History row on top of the real one. Now it
        // is Unmeasured — the first traversal is still recorded exactly as
        // before, and the rejoin adds nothing.
        val trace = generateReentryTrace(
            TRAKIYA_T10,
            speedKmh = 130.0,
            exitAtFraction = 0.3,
            offRoadDurationMs = 120_000L,
        )

        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val entrySnapshots = mutableListOf<ZoneState.InZone>()
        var prevEntryTime: Long? = null
        var exits = 0
        var sawUnmeasuredAfterExit = false

        for (point in trace) {
            val state = det.update(point)
            if (state is ZoneState.InZone) {
                if (prevEntryTime == null || state.entryTime != prevEntryTime) {
                    entrySnapshots.add(state)
                    prevEntryTime = state.entryTime
                }
            } else {
                prevEntryTime = null
                if (state is ZoneState.Exiting) exits++
                if (state is ZoneState.Unmeasured && exits > 0) sawUnmeasuredAfterExit = true
            }
        }

        assertEquals(1, entrySnapshots.size,
            "The rejoin never crossed the entry camera, so exactly one measured " +
                "traversal must exist, got ${entrySnapshots.size}")
        assertEquals(1, exits, "Exactly one traversal should have been finalized")
        assertTrue(sawUnmeasuredAfterExit,
            "Rejoining the road mid-zone must surface as Unmeasured, not silence")
    }

    @Test
    fun `re-entry after timestamp rewind starts fresh`() {
        // Simulates the AAOS emulator restarting a GPX replay: after driving
        // partway through the zone, subsequent points arrive with timestamps
        // earlier than the exit. The detector must treat this as a fresh entry,
        // not resume stale progress.
        val det = ZoneDetector(listOf(TRAKIYA_T10))

        // Phase 1: drive partway through the zone.
        val trace1 = generateGpsTrace(TRAKIYA_T10, speedKmh = 130.0, startTime = EPOCH_BASE)
        var firstEntryTime: Long? = null
        var firstMaxDistance = 0.0
        for (point in trace1.take(20)) {
            val state = det.update(point)
            if (state is ZoneState.InZone) {
                if (firstEntryTime == null) firstEntryTime = state.entryTime
                firstMaxDistance = maxOf(firstMaxDistance, state.distanceTraveled)
            }
        }
        assertTrue(firstEntryTime != null, "Should have entered zone in phase 1")
        assertTrue(firstMaxDistance > 100,
            "Should have accumulated some distance in phase 1 (got $firstMaxDistance)")

        // Phase 2: force exit via an off-road point.
        val offRoadTime = trace1[19].timestamp + 1000
        det.update(GpsPoint(42.6, 23.9, 80.0, offRoadTime, 180.0))

        // Phase 3: replay the GPX with timestamps earlier than the exit time.
        val trace2 = generateGpsTrace(
            TRAKIYA_T10,
            speedKmh = 130.0,
            startTime = firstEntryTime!! - 60_000L,
        )
        var rewoundEntryTime: Long? = null
        var rewoundInitialDistance: Double? = null
        for (point in trace2.take(20)) {
            val state = det.update(point)
            if (state is ZoneState.InZone && rewoundEntryTime == null) {
                rewoundEntryTime = state.entryTime
                rewoundInitialDistance = state.distanceTraveled
            }
        }

        assertTrue(rewoundEntryTime != null, "Should have re-entered zone after rewind")
        assertTrue(rewoundEntryTime!! < firstEntryTime!!,
            "Rewound entry time $rewoundEntryTime should be before original $firstEntryTime")
        // Starts from its own confirmation window (see `re-entry always starts
        // fresh`), never resuming phase 1's progress.
        assertTrue(rewoundInitialDistance!! <= ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 1.5,
            "Re-entry after rewind should start from its own confirmation window, " +
                "got $rewoundInitialDistance")
        assertTrue(rewoundInitialDistance!! < firstMaxDistance,
            "Re-entry after rewind must not resume phase 1's progress " +
                "($rewoundInitialDistance vs $firstMaxDistance)")
    }

    @Test
    fun `noisy GPS trace still detects zone`() {
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 130.0)
        val noisyTrace = addNoiseToTrace(trace, noiseMeters = 15.0)

        var sawInZone = false
        var sawExiting = false
        for (point in noisyTrace) {
            val state = detector.update(point)
            if (state is ZoneState.InZone) sawInZone = true
            if (state is ZoneState.Exiting) sawExiting = true
        }

        assertTrue(sawInZone, "Noisy trace should still detect zone entry")
        assertTrue(sawExiting, "Noisy trace should still detect zone exit")
    }

    @Test
    fun `very high speed traversal works correctly`() {
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 220.0)

        var sawInZone = false
        var sawExiting = false
        var lastExitState: ZoneState.Exiting? = null

        for (point in trace) {
            val state = detector.update(point)
            if (state is ZoneState.InZone) sawInZone = true
            if (state is ZoneState.Exiting) {
                sawExiting = true
                lastExitState = state
            }
        }

        assertTrue(sawInZone, "Should enter zone at high speed")
        assertTrue(sawExiting, "Should exit zone at high speed")
        assertTrue(lastExitState!!.finalAvgSpeed!! > 150, "High speed should register")
        assertTrue(lastExitState.finalAvgSpeed!! > 140, "220 km/h should be over 140 limit")
    }

    @Test
    fun `dense short-segment zone is a single clean traversal (no integrator drift exit)`() {
        // Regression for the qa/feed-zone.sh bug: a zone with a densely-sampled
        // centerline (segments far shorter than the per-second travel distance)
        // driven with a constant reported speed made the speed×time integrator
        // over-count distance. The old engine then (a) collapsed
        // maxSpeedForRemainder to 0 mid-zone and (b) tripped the
        // `distanceTraveled >= distanceM * 1.1` exit, immediately re-entering as a
        // mid-zone cold-start and resetting the stats. The fix sources remaining
        // distance + the exit decision from the polyline projection.
        val zone = denseShortSegmentZone(distanceM = 2300, segmentM = 15.0, speedLimitCar = 140)
        // 108 km/h reported vs ~54 km/h real geographic speed → 2× integrator over-count.
        val trace = generateUnevenSpacingTrace(zone, reportedSpeedKmh = 108.0)
        val det = ZoneDetector(listOf(zone))

        val entryTimes = linkedSetOf<Long>()
        var sawExiting = false
        var collapsedEarly = false
        var sawUnmeasured = false
        for (point in trace) {
            when (val state = det.update(point)) {
                is ZoneState.Unmeasured -> sawUnmeasured = true
                is ZoneState.InZone -> {
                    entryTimes.add(state.entryTime)
                    // While there is meaningful road left, the remainder speed must
                    // not collapse to 0 (it would, the moment the drifted integrator
                    // passed the zone distance).
                    if (state.distanceRemaining > ZoneDetector.EXIT_DISTANCE_M &&
                        state.speedStatus.maxSpeedForRemainder <= 0.0
                    ) {
                        collapsedEarly = true
                    }
                }
                is ZoneState.Exiting -> sawExiting = true
                is ZoneState.Outside -> {}
            }
        }

        assertFalse(collapsedEarly,
            "maxSpeedForRemainder collapsed to 0 while road remained — integrator drift leaked in")
        assertEquals(1, entryTimes.size,
            "Expected a single uninterrupted traversal, but the zone was (re-)entered ${entryTimes.size} times")
        assertTrue(sawExiting, "Should have cleanly exited at the zone end")
        assertFalse(sawUnmeasured, "Witnessed entry must not degrade to Unmeasured")
    }

    @Test
    fun `reversed-centerline zone still enters the correct sibling (qa feed-zone 0 bug)`() {
        // Regression for `qa/feed-zone.sh 0` (europa-01-north): the server serves
        // the north zone's centerline stored END-FIRST. Its raw first→last bearing
        // then points the way the SOUTH sibling travels, so a northbound drive used
        // to match `europa-test-south` (the "red dot first" the user reported) and
        // report an inverted "remaining". The engine now orients each centerline to
        // its start/end endpoints, so it recovers regardless of stored point order.
        val (north, south) = europaReversedSiblings()
        // List south first so a buggy detector that ignores direction would have it
        // available to (wrongly) win.
        val det = ZoneDetector(listOf(south, north))
        val trace = europaNorthboundTrace(speedKmh = 108.0)

        val inZoneIds = mutableListOf<String>()
        var firstInZoneId: String? = null
        var exitedId: String? = null
        var unmeasuredId: String? = null
        for (point in trace) {
            when (val state = det.update(point)) {
                is ZoneState.InZone -> {
                    if (firstInZoneId == null) firstInZoneId = state.zone.id
                    inZoneIds.add(state.zone.id)
                }
                is ZoneState.Exiting -> exitedId = state.zone.id
                is ZoneState.Unmeasured -> unmeasuredId = state.zone.id
                is ZoneState.Outside -> {}
            }
        }
        assertEquals(
            null, unmeasuredId,
            "Re-orienting the reversed centerline must also restore the arc origin, " +
                "so the approach is witnessed and the traversal measurable",
        )

        assertTrue(inZoneIds.isNotEmpty(), "Should have entered a zone")
        assertEquals(
            "europa-test-north", firstInZoneId,
            "First in-zone fix matched the wrong sibling — the reversed centerline " +
                "flipped the detected direction (the 'red dot first' bug)",
        )
        assertTrue(
            inZoneIds.all { it == "europa-test-north" },
            "Whole northbound traversal must stay europa-test-north, saw: ${inZoneIds.distinct()}",
        )
        assertEquals("europa-test-north", exitedId, "Should cleanly exit the north zone")
    }

    @Test
    fun `reversed-centerline zone reports a decreasing, non-inverted remaining`() {
        // The same end-first centerline also inverts the polyline "remaining"
        // (full at the physical end, ~0 at the start) unless projection is done
        // against the endpoint-oriented centerline.
        val (north, _) = europaReversedSiblings()
        val det = ZoneDetector(listOf(north))
        val trace = europaNorthboundTrace(speedKmh = 108.0)

        val remaining = mutableListOf<Double>()
        for (point in trace) {
            (det.update(point) as? ZoneState.InZone)?.let { remaining.add(it.distanceRemaining) }
        }

        assertTrue(remaining.size >= 3, "Need several in-zone samples")
        // Starts near the full zone length, not near 0 (which an inverted reading
        // would give right after entry).
        assertTrue(
            remaining.first() > north.distanceM * 0.5,
            "Remaining at entry should be most of the zone, was ${remaining.first()}",
        )
        assertTrue(
            remaining.last() < remaining.first(),
            "Remaining should decrease toward the end, not invert",
        )
    }

    @Test
    fun `vehicle type changes effective limit`() {
        // Vehicle-type-aware ZoneDetector (backported from iOS). A truck on a
        // 140 km/h motorway is limited to 90 km/h, so 120 km/h must register as
        // over-limit for a truck but not for a car.
        val trace = generateGpsTrace(TRAKIYA_T10, speedKmh = 120.0)
        val carDetector = ZoneDetector(listOf(TRAKIYA_T10))
        val truckDetector = ZoneDetector(listOf(TRAKIYA_T10))

        var carLast: ZoneState.InZone? = null
        var truckLast: ZoneState.InZone? = null
        for (point in trace) {
            (carDetector.update(point, VehicleType.CAR) as? ZoneState.InZone)?.let { carLast = it }
            (truckDetector.update(point, VehicleType.TRUCK) as? ZoneState.InZone)?.let { truckLast = it }
        }

        assertFalse(carLast == null, "Car should have been in zone")
        assertFalse(truckLast == null, "Truck should have been in zone")
        assertFalse(carLast!!.speedStatus.isOverLimit, "Car at 120 in 140 zone is fine")
        assertTrue(truckLast!!.speedStatus.isOverLimit, "Truck at 120 in 90 (truck) zone is over limit")
    }

    @Test
    fun `motorway zone matches at wider distance`() {
        // Trakiya is a motorway (road starts with "АМ ")
        // Point 120m from centerline — should match motorway (150m threshold) but not national road (100m threshold)
        val midBearing = polylineBearing(TRAKIYA_T10.centerline)
        // Point 120m perpendicular to the first segment of Trakiya
        val offsetLat = 120.0 / 111_320.0
        val nearPoint = GpsPoint(
            lat = TRAKIYA_T10.start.lat + offsetLat,
            lng = TRAKIYA_T10.start.lng,
            speed = 130.0,
            timestamp = EPOCH_BASE,
            bearing = midBearing,
        )

        val onMotorway = RoadMatcher.isOnRoad(nearPoint, TRAKIYA_T10)
        assertTrue(onMotorway, "120m from motorway centerline should be on road (150m threshold)")

        val onNational = RoadMatcher.isOnRoad(nearPoint, I4_10)
        // I4 is far away, so this won't match regardless. Test with a nearby national road instead.
        val nearNationalPoint = GpsPoint(
            lat = NATIONAL_ROAD_ZONE.centerline[0][0] + offsetLat,
            lng = NATIONAL_ROAD_ZONE.centerline[0][1],
            speed = 80.0,
            timestamp = EPOCH_BASE,
            bearing = 90.0,
        )
        val onNationalRoad = RoadMatcher.isOnRoad(nearNationalPoint, NATIONAL_ROAD_ZONE)
        assertFalse(onNationalRoad, "120m from national road centerline should NOT be on road (100m threshold)")
    }

    @Test
    fun `empty zone list never enters a zone`() {
        val empty = ZoneDetector(emptyList())
        val point = GpsPoint(
            lat = TRAKIYA_T10.start.lat, lng = TRAKIYA_T10.start.lng,
            speed = 130.0, timestamp = EPOCH_BASE, bearing = polylineBearing(TRAKIYA_T10.centerline),
        )
        // No zones to match — stays Outside across repeated fixes, no crash.
        assertTrue(empty.update(point) is ZoneState.Outside)
        assertTrue(empty.update(point.copy(timestamp = EPOCH_BASE + 1000L)) is ZoneState.Outside)
    }

    @Test
    fun `road clipping the band on a matching heading never opens a traversal`() {
        // Regression for the phantom I-1 traversal (real drive, 2026-07-26,
        // reproduced on both platforms). The A3 Струма motorway runs within 15 m
        // of the i1-02-north centerline for ~190 m at the Кочериново
        // interchange, on a heading inside DIRECTION_TOLERANCE_DEG. A single
        // band-clipping fix opened a *full* traversal of the 10.6 km zone —
        // entry announcement, junk History record — that then exited seconds
        // later when the motorway pulled away.
        val det = ZoneDetector(listOf(TRAKIYA_T10))

        // A neighbouring carriageway: inside the on-road band, running parallel,
        // but only for less than the confirmation distance.
        val clip = collectAlongCenterline(
            det, TRAKIYA_T10,
            fromArcM = 2_000.0,
            metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 0.6,
            lateralOffsetM = 60.0,
        )
        assertTrue(
            clip.all { it is ZoneState.Outside },
            "A road clipping the band for less than ENTRY_CONFIRM_DISTANCE_M must " +
                "never open a traversal, got ${clip.firstOrNull { it !is ZoneState.Outside }}",
        )

        // …and once it peels away the detector is still Outside, with nothing to
        // exit from (no phantom Exiting, so no History record / exit announcement).
        val awayTime = EPOCH_BASE + 60_000L
        val away = det.update(GpsPoint(42.6, 23.9, 130.0, awayTime, 180.0))
        assertTrue(away is ZoneState.Outside, "Peeling away must stay Outside, got $away")
    }

    @Test
    fun `sustained travel along the zone still enters, back-dated to the first fix`() {
        // The other half of the guard above: a car genuinely on the road must
        // still enter, and must not be charged for the confirmation window —
        // the traversal is back-dated to the first confirming fix, so the
        // average covers the whole drive.
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        // Start on the approach road, before the entry camera: the traversal is
        // only measurable if we watched the start line being crossed.
        val states = collectAlongCenterline(
            det, TRAKIYA_T10,
            fromArcM = -200.0,
            metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 2 + 200.0,
        )
        val entered = states.filterIsInstance<ZoneState.InZone>().firstOrNull()
        assertTrue(entered != null, "Sustained travel along the centerline must enter the zone")

        // Back-dating means the recorded entry is the first fix that *matched* the
        // zone (a couple of fixes into the approach, once we are inside the
        // on-road band), not the much later fix at which confirmation completed.
        val stepMs = (36.0 / (130.0 / 3.6) * 1000.0).toLong()
        val flipTime = EPOCH_BASE + states.indexOfFirst { it is ZoneState.InZone } * stepMs
        val backDatedByMs = flipTime - entered!!.entryTime
        val confirmMs = (ZoneDetector.ENTRY_CONFIRM_DISTANCE_M / (130.0 / 3.6) * 1000.0).toLong()
        assertTrue(backDatedByMs >= confirmMs * 0.8,
            "Traversal must be back-dated across the confirmation window — expected " +
                "at least ${(confirmMs * 0.8).toLong()}ms, got ${backDatedByMs}ms")
        assertTrue(entered.distanceTraveled >= ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 0.8,
            "Back-dated entry must carry the ground covered during confirmation, " +
                "got ${entered.distanceTraveled}")
    }

    @Test
    fun `co-located camera hands over to the next zone immediately`() {
        // At a co-located pair (24 in the data) one camera ends zone A and
        // begins zone B, so there is no room to re-confirm B — and no need:
        // driving A to its end IS the evidence. B must open on the very next
        // fix, keeping the InZone(A) -> Exiting(A) -> InZone(B) handover the
        // TTS layer relies on for the chained exit/entry announcement.
        val zoneA = TRAKIYA_T10
        val zoneB = nextZoneFrom(zoneA, id = "trakiya-02-west", lengthM = 6_000.0)
        val det = ZoneDetector(listOf(zoneA, zoneB))

        // Drive the whole of A, from before its entry camera up to the shared one.
        // Starting mid-zone would make A Unmeasured, and an Unmeasured zone never
        // reaches exitZone, so it never offers the handover this test is about.
        val stepM = 36.0
        val speed = 130.0
        val stepMs = (stepM / (speed / 3.6) * 1000.0).toLong()
        val total = polylineLengthMeters(zoneA.centerline)
        val statesA = collectAlongCenterline(
            det, zoneA, fromArcM = -200.0, metres = total + 200.0,
            speedKmh = speed, stepM = stepM,
        )
        assertTrue(statesA.any { it is ZoneState.InZone && it.zone.id == zoneA.id },
            "Should have driven zone A")
        assertTrue(statesA.any { it is ZoneState.Exiting }, "Should have exited zone A at its end")

        // …then straight on into B, which starts at that same camera.
        val statesB = collectAlongCenterline(
            det, zoneB, fromArcM = 0.0, metres = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M,
            speedKmh = speed, stepM = stepM,
            startTime = EPOCH_BASE + statesA.size * stepMs,
        )
        val enterBIdx = statesB.indexOfFirst { it is ZoneState.InZone && it.zone.id == zoneB.id }
        assertTrue(enterBIdx >= 0, "Co-located zone B must open after A's exit, got $statesB")

        // The bypass is the point: B opens well inside the distance a normal
        // confirmation would have cost, so the driver gets the new limit at the
        // camera rather than a few hundred metres past it.
        val handoverM = enterBIdx * stepM
        assertTrue(
            handoverM < ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 0.5,
            "Co-located handover took ${handoverM.toInt()} m — no better than the " +
                "normal ${ZoneDetector.ENTRY_CONFIRM_DISTANCE_M.toInt()} m confirmation",
        )
    }

    @Test
    fun `GPS dropout does not deflate the reported average`() {
        // Regression for the "24 km/h" History record (real drive, 2026-07-26):
        // the integrator skipped the dropout gap while elapsed time kept
        // counting it, so ~6 s of credited distance divided by 21 s of elapsed
        // turned an ~87 km/h drive into a reported 24 km/h. Across a dropout the
        // distance is now bridged from the centerline projection.
        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val speed = 90.0
        val speedMs = speed / 3.6
        val stepM = 25.0
        val stepMs = (stepM / speedMs * 1000.0).toLong()
        // Approach from before the entry camera so the traversal is measurable at
        // all (see START_WITNESS_ARC_M) — the dropout behaviour under test only
        // exists inside a measured traversal.
        val startArc = -200.0
        val drivenM = ZoneDetector.ENTRY_CONFIRM_DISTANCE_M * 1.5 + 200.0

        val states = collectAlongCenterline(
            det, TRAKIYA_T10,
            fromArcM = startArc, metres = drivenM,
            speedKmh = speed, stepM = stepM,
        )
        assertTrue(states.last() is ZoneState.InZone, "Should be in the zone before the dropout")
        val lastArc = startArc + (states.size - 1) * stepM
        val lastTime = EPOCH_BASE + (states.size - 1) * stepMs

        // 15 s of silence, during which the car covers 375 m of road at the same
        // steady speed.
        val dropoutMs = 15_000L
        val resumeArc = lastArc + speedMs * (dropoutMs / 1000.0)
        val resumeAt = pointAtArcLength(TRAKIYA_T10.centerline, resumeArc)
        val resumed = det.update(
            GpsPoint(
                lat = resumeAt[0], lng = resumeAt[1], speed = speed,
                timestamp = lastTime + dropoutMs,
                bearing = localPolylineBearing(
                    TRAKIYA_T10.centerline, resumeArc, RoadMatcher.LOCAL_BEARING_WINDOW_M,
                )!!,
            ),
        ) as ZoneState.InZone

        val avg = resumed.speedStatus.avgSpeed!!
        assertTrue(avg > speed * 0.85,
            "A GPS dropout must not deflate the average — driving a steady $speed km/h " +
                "through a ${dropoutMs}ms gap reported $avg km/h")
    }

    @Test
    fun `degenerate single-point centerline never matches`() {
        // A zone whose centerline has a single point can't yield a bearing or a
        // meaningful distance band, so it must never be entered (matchDirection /
        // isOnRoad both require >= 2 points) — and must not crash construction.
        val degenerate = TRAKIYA_T10.copy(
            id = "degenerate-01",
            centerline = listOf(listOf(42.427, 23.855)),
        )
        val detector = ZoneDetector(listOf(degenerate))
        val onPoint = GpsPoint(
            lat = 42.427, lng = 23.855, speed = 130.0,
            timestamp = EPOCH_BASE, bearing = 300.0,
        )
        assertTrue(detector.update(onPoint) is ZoneState.Outside)
    }
}
