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

        for (point in trace) {
            val state = detector.update(point)
            when (state) {
                is ZoneState.Outside -> sawOutside = true
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
    fun `cold-start mid-zone enters with reduced effective distance`() {
        // Point on the centerline well inside the zone, beyond the start buffer but
        // not yet at the end. Simulates user opening the app while already driving
        // through a zone.
        val midBearing = polylineBearing(TRAKIYA_T10.centerline)
        val midPoint = GpsPoint(
            lat = 42.510, lng = 23.770, speed = 130.0,
            timestamp = EPOCH_BASE, bearing = midBearing,
        )

        val state = detector.update(midPoint)
        assertTrue(state is ZoneState.InZone, "Should enter zone from mid-point cold-start")
        val inZone = state as ZoneState.InZone
        // distanceRemaining is polyline arc-length to zone.end (drives the UI label
        // and progress bar). Must be strictly less than the full zone length and
        // meaningful (not pinned to 0).
        assertTrue(inZone.distanceRemaining < TRAKIYA_T10.distanceM,
            "Polyline-remaining ${inZone.distanceRemaining} should be less than full zone ${TRAKIYA_T10.distanceM}")
        assertTrue(inZone.distanceRemaining > 1000,
            "Mid-zone cold-start should still have meaningful distance remaining (${inZone.distanceRemaining})")
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

        // Feed a few points to enter the zone
        var enteredZone = false
        for (point in trace.take(10)) {
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
    fun `re-entry always starts fresh`() {
        // Drive into zone, leave the road to trigger an exit, then return.
        // Re-entry must anchor to the new entry point: fresh entryTime and
        // near-zero distanceTraveled, regardless of how recently we exited.
        val trace = generateReentryTrace(
            TRAKIYA_T10,
            speedKmh = 130.0,
            exitAtFraction = 0.3,
            offRoadDurationMs = 120_000L,
        )

        val det = ZoneDetector(listOf(TRAKIYA_T10))
        val entrySnapshots = mutableListOf<ZoneState.InZone>()
        var prevEntryTime: Long? = null

        for (point in trace) {
            val state = det.update(point)
            if (state is ZoneState.InZone) {
                if (prevEntryTime == null || state.entryTime != prevEntryTime) {
                    entrySnapshots.add(state)
                    prevEntryTime = state.entryTime
                }
            } else {
                prevEntryTime = null
            }
        }

        assertTrue(entrySnapshots.size >= 2,
            "Should have entered zone twice (initial + re-entry), got ${entrySnapshots.size}")
        val first = entrySnapshots.first()
        val reentry = entrySnapshots.last()
        assertTrue(reentry.entryTime > first.entryTime,
            "Re-entry time ${reentry.entryTime} should be after initial ${first.entryTime}")
        assertTrue(reentry.distanceTraveled < 5.0,
            "Re-entry should start with ~0 distanceTraveled, got ${reentry.distanceTraveled}")
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
        assertTrue(rewoundInitialDistance!! < 5.0,
            "Re-entry after rewind should start with ~0 distance, got $rewoundInitialDistance")
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
        for (point in trace) {
            when (val state = det.update(point)) {
                is ZoneState.InZone -> {
                    entryTimes.add(state.entryTime)
                    // While there is meaningful road left, the remainder speed must
                    // not collapse to 0 (it would, the moment the drifted integrator
                    // passed effectiveZoneDistance).
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
        for (point in trace) {
            when (val state = det.update(point)) {
                is ZoneState.InZone -> {
                    if (firstInZoneId == null) firstInZoneId = state.zone.id
                    inZoneIds.add(state.zone.id)
                }
                is ZoneState.Exiting -> exitedId = state.zone.id
                is ZoneState.Outside -> {}
            }
        }

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
}
