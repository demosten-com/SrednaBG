// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Testing
@testable import SrednaBGCore

/// Entry provenance: a traversal is only measurable if we watched the vehicle
/// cross the start line. Everything else inside a zone is `.unmeasured` — we say
/// which zone it is and how much road is left, and nothing else.
///
/// Mirrors the Kotlin `ZoneUnmeasuredTest`; split out of `ZoneDetectorTests` for
/// the same reason `ZoneEntryConfirmationTests` was (SwiftLint file length).
///
/// See `ZoneDetector.startWitnessArcM`.
@Suite("ZoneUnmeasured")
struct ZoneUnmeasuredTests {

    @Test func joiningMidZoneNeverOpensATraversalAndNeverExitsOne() {
        // The core of the change: a sustained, perfectly on-road drive that simply
        // began too far into the zone. It confirms (300 m of travel along the
        // centerline) but is not witnessed, so it graduates into `.unmeasured`
        // rather than `.inZone` — and leaving it produces no `.exiting`, which is
        // what keeps it out of History and out of the exit announcement without
        // any suppression logic at the consumer layers.
        var det = ZoneDetector(zones: [TRAKIYA_T10])
        let states = collectAlongCenterline(
            &det, TRAKIYA_T10,
            fromArcM: 5_000,
            metres: ZoneDetector.entryConfirmDistanceM * 3
        )

        #expect(states.contains { if case .unmeasured = $0 { return true } else { return false } })
        #expect(!states.contains { if case .inZone = $0 { return true } else { return false } },
                "Must never open a measured traversal")
        #expect(!states.contains { if case .exiting = $0 { return true } else { return false } },
                "Must never produce an .exiting")

        // Peel off the road: unmeasured drops straight to outside.
        let away = det.update(GpsPoint(lat: 42.9, lng: 24.4, speed: 130, timestamp: epochBase + 600_000, bearing: 180))
        #expect(away == .outside, "Leaving an unmeasured zone goes straight to .outside")
    }

    @Test func drivingAnUnmeasuredZoneToItsEndLandsOnOutsideNotExiting() {
        // `.exiting` only ever follows `.inZone`: there is no traversal to
        // finalize, so reaching the end camera is not an exit. Locks the invariant
        // the consumer layers rely on (no History row, no exit TTS).
        var det = ZoneDetector(zones: [TRAKIYA_T10])
        let total = polylineLengthMeters(TRAKIYA_T10.centerline)
        let startArc = 6_000.0
        let states = collectAlongCenterline(
            &det, TRAKIYA_T10,
            fromArcM: startArc,
            metres: total - startArc
        )

        #expect(states.contains { if case .unmeasured = $0 { return true } else { return false } })
        #expect(!states.contains { if case .exiting = $0 { return true } else { return false } },
                "Reaching the end of an unmeasured zone must not fabricate an .exiting")
        #expect(states.last == .outside, "Should have ended .outside")
    }

    @Test func aColocatedSuccessorIsStillMeasurableAfterAnUnmeasuredPredecessor() {
        // A driver who joined A mid-way still physically crosses B's entry camera,
        // so B is genuinely measurable and must open normally. What does not carry
        // over is the `colocatedCameraM` confirmation bypass — that is armed in
        // `exitZone`, which an unmeasured zone never reaches — so B pays the
        // ordinary 300 m confirmation. Roughly 10 s of announcement latency in a
        // rare case; deliberately not special-cased.
        let zoneA = TRAKIYA_T10
        let zoneB = nextZoneFrom(zoneA, id: "trakiya-02-west", lengthM: 6_000)
        var det = ZoneDetector(zones: [zoneA, zoneB])

        let stepM = 36.0
        let speed = 130.0
        let stepMs = Int64(stepM / (speed / 3.6) * 1000.0)
        let totalA = polylineLengthMeters(zoneA.centerline)
        let startArcA = 4_000.0

        let statesA = collectAlongCenterline(
            &det, zoneA, fromArcM: startArcA, metres: totalA - startArcA,
            speedKmh: speed, stepM: stepM
        )
        #expect(statesA.contains {
            if case .unmeasured(let u) = $0 { return u.zone.id == zoneA.id } else { return false }
        }, "Zone A was joined mid-way, so it must be unmeasured")
        #expect(!statesA.contains { if case .inZone = $0 { return true } else { return false } },
                "Zone A must not be measured")

        let statesB = collectAlongCenterline(
            &det, zoneB, fromArcM: 0, metres: ZoneDetector.entryConfirmDistanceM * 2,
            speedKmh: speed, stepM: stepM,
            startTime: epochBase + Int64(statesA.count) * stepMs
        )
        #expect(statesB.contains {
            if case .inZone(let z) = $0 { return z.zone.id == zoneB.id } else { return false }
        }, "Zone B's entry camera *was* crossed, so B must be measured")
        #expect(!statesB.contains { if case .unmeasured = $0 { return true } else { return false } },
                "Zone B starts at arc 0 — it must never read as a mid-zone join")
    }

    @Test func aColocatedHandoverCountsAsWitnessedEvenWhenTheFirstFixLandsLate() {
        // Driving A to its end IS crossing B's start camera, so a handover is
        // witnessed by construction — whatever arc B's first fix happens to land
        // at. Without the `|| handedOver` clause a coarse fix right after the
        // shared camera could downgrade a genuinely measurable zone to unmeasured
        // and silently swallow its entry announcement.
        //
        // The gap below is synthetic (a real handover lands within a few tens of
        // metres); it exists to put the first fix on B past `startWitnessArcM` on
        // purpose.
        let zoneA = TRAKIYA_T10
        let zoneB = nextZoneFrom(zoneA, id: "trakiya-02-west", lengthM: 6_000)
        var det = ZoneDetector(zones: [zoneA, zoneB])

        let stepM = 36.0
        let speed = 130.0
        let stepMs = Int64(stepM / (speed / 3.6) * 1000.0)
        let totalA = polylineLengthMeters(zoneA.centerline)
        let statesA = collectAlongCenterline(
            &det, zoneA, fromArcM: -200, metres: totalA + 200,
            speedKmh: speed, stepM: stepM
        )
        #expect(statesA.contains { if case .exiting = $0 { return true } else { return false } },
                "Zone A must have exited")

        let statesB = collectAlongCenterline(
            &det, zoneB, fromArcM: ZoneDetector.startWitnessArcM * 1.5, metres: stepM * 2,
            speedKmh: speed, stepM: stepM,
            startTime: epochBase + Int64(statesA.count) * stepMs
        )
        #expect({ if case .inZone = statesB[0] { return true } else { return false } }(),
                "A handover must open B immediately and measured")
        #expect(!statesB.contains { if case .unmeasured = $0 { return true } else { return false } },
                "A handover is witnessed by construction — it must never yield .unmeasured")
    }

    @Test func theOppositeCarriagewaySiblingCannotClaimTheColocatedHandover() {
        // At a co-located camera the *westbound* sibling also starts within
        // `colocatedCameraM` of the eastbound zone's end — trakiya-03-west's
        // start is 15 m from trakiya-03-east's end, which is also
        // trakiya-04-east's start. Proximity alone therefore lets the sibling
        // claim the confirmation bypass, and a single wrong-bearing fix at the
        // seam is enough to open a *measured* traversal of the zone running back
        // the way we came — complete with an entry announcement.
        //
        // That wrong-bearing fix is not hypothetical: trakiya-04-east's stored
        // centerline opens with a 19 m segment bearing west (ISSUE-001), so a
        // route following the geometry genuinely reads as westbound for one fix.
        // Found by qa/colocated-zones.sh --all (7/24 pairs).
        let zoneA = TRAKIYA_T10
        var sibling = TRAKIYA_T10_OPPOSITE
        sibling = Zone(
            id: "trakiya-01-west-sibling",
            road: sibling.road,
            roadLatin: sibling.roadLatin,
            direction: sibling.direction,
            description: sibling.description,
            start: zoneA.end,
            end: zoneA.start,
            distanceM: sibling.distanceM,
            speedLimits: sibling.speedLimits,
            centerline: zoneA.centerline.reversed(),
            source: sibling.source,
            lastVerified: sibling.lastVerified
        )
        var det = ZoneDetector(zones: [zoneA, sibling])

        let stepM = 36.0
        let speed = 130.0
        let stepMs = Int64(stepM / (speed / 3.6) * 1000.0)
        let total = polylineLengthMeters(zoneA.centerline)
        let statesA = collectAlongCenterline(
            &det, zoneA, fromArcM: -200, metres: total + 200,
            speedKmh: speed, stepM: stepM
        )
        #expect(statesA.contains { if case .exiting = $0 { return true } else { return false } },
                "Zone A must have exited")

        // One fix at the shared camera carrying the sibling's heading — the seam
        // artifact. It must NOT open a measured traversal of the sibling.
        let siblingStates = collectAlongCenterline(
            &det, sibling, fromArcM: 0, metres: stepM,
            speedKmh: speed, stepM: stepM,
            startTime: epochBase + Int64(statesA.count) * stepMs
        )
        #expect(!siblingStates.contains { if case .inZone = $0 { return true } else { return false } },
                "The opposite-carriageway sibling must not claim the handover bypass")
    }

    @Test func aZoneWhoseCenterlineStartsWithABackwardsJogIsStillMeasurable() throws {
        // The regression a 100 m `startWitnessArcM` would have caused. On
        // i3-02-north, i6-01-east and trakiya-03-east the stored centerline opens
        // with a segment running ~180 degrees against the road (ISSUE-001), so an
        // honest approach projects onto the far end of that jog rather than to
        // arc 0. Measured across all 72 bundled zones, the worst first-match arc
        // on a legitimate approach is 121 m (2 s cadence) / 148 m (5 s cold-start
        // cadence) — both at i3-02-north, whose jog this fixture reproduces.
        //
        // If this test starts failing, `startWitnessArcM` has been tightened past
        // what the shipped geometry supports and those zones will report "not
        // measured" on every real drive.
        let zone = jogStartZone(jogM: 121)
        var det = ZoneDetector(zones: [zone])

        let trace = jogStartRoadTrace(
            fromM: -250,
            toM: ZoneDetector.entryConfirmDistanceM * 2
        )

        // Non-vacuity guard: the fixture has to actually exhibit the hazard. The
        // arc of the first fix that matches the zone at all is exactly what
        // decides provenance, so assert it sits in the danger band — past the
        // 100 m originally proposed, inside the 200 m actually chosen.
        let firstMatchArc = trace.lazy.compactMap { point -> Double? in
            guard RoadMatcher.findMatchingZone(point, [zone]) != nil else { return nil }
            return arcLengthOnPolyline(point.lat, point.lng, zone.centerline)
        }.first
        let arc = try #require(firstMatchArc, "Fixture never matches the zone at all")
        #expect(arc > 100,
                """
                Fixture no longer reproduces the ISSUE-001 jog — first matching fix projects to \
                arc \(arc), so a 100 m threshold would pass too and this test proves nothing
                """)
        #expect(arc <= ZoneDetector.startWitnessArcM,
                "First matching fix projects to arc \(arc), past startWitnessArcM")

        let states = trace.map { det.update($0) }
        #expect(states.contains { if case .inZone = $0 { return true } else { return false } },
                "A genuine approach to a jog-start zone must still be measured")
        #expect(!states.contains { if case .unmeasured = $0 { return true } else { return false } },
                """
                The backwards start jog must not be mistaken for a mid-zone join — \
                startWitnessArcM (\(ZoneDetector.startWitnessArcM)) is too tight
                """)
    }

    @Test func unmeasuredCarriesTheZoneAndTheRoadLeftAndNothingDerivedFromTiming() {
        // What this state may show is the road's own facts: which zone it is (and
        // therefore its speed limit, the same thing the physical sign says) and
        // how much of it is left. There is deliberately no average, no
        // max-for-remainder and no elapsed time to render — structural, enforced
        // by the type rather than by convention.
        var det = ZoneDetector(zones: [TRAKIYA_T10])
        let startArc = 5_000.0
        let states = collectAlongCenterline(
            &det, TRAKIYA_T10,
            fromArcM: startArc,
            metres: ZoneDetector.entryConfirmDistanceM * 2
        )

        guard case .unmeasured(let unmeasured) = states[states.count - 1] else {
            Issue.record("Expected .unmeasured, got \(String(describing: states.last))")
            return
        }
        #expect(unmeasured.zone.id == TRAKIYA_T10.id)
        #expect(unmeasured.zone.speedLimits.car == 140, "The limit must survive — it is a road fact")

        let total = polylineLengthMeters(TRAKIYA_T10.centerline)
        let expected = total - (startArc + ZoneDetector.entryConfirmDistanceM * 2)
        #expect(abs(unmeasured.distanceRemaining - expected) < 100,
                """
                distanceRemaining should track the polyline arc to the end — \
                expected ~\(expected), got \(unmeasured.distanceRemaining)
                """)
    }
}
