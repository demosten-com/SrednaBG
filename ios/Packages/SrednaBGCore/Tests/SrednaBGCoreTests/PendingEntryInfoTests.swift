// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation
import Testing
@testable import SrednaBGCore

/// The entry-candidate side channel (`ZoneDetector.pendingEntryInfo`) that the
/// announcement layer speaks from, so the driver hears the entry where they
/// cross the camera rather than `ZoneDetector.entryConfirmDistanceM` later.
///
/// Mirrors Kotlin `PendingEntryInfoTest` case for case. Pins the two properties
/// the announcement depends on: the candidate appears on the **first** matching
/// fix while the state is still `.outside`, and its `entryArcM` is the same
/// value `witnessedStart` will later judge — so applying `startWitnessArcM` to
/// it predicts, before confirmation, whether this candidate can become a
/// measured traversal.
@Suite("PendingEntryInfo")
struct PendingEntryInfoTests {

    @Test
    func noCandidateExistsWhileNoZoneMatches() {
        var det = ZoneDetector(zones: [TRAKIYA_T10])
        #expect(det.pendingEntryInfo == nil, "A fresh detector has no candidate")

        _ = det.update(GpsPoint(lat: 42.0, lng: 23.0, speed: 130, timestamp: epochBase, bearing: 90))
        #expect(det.pendingEntryInfo == nil, "An unmatched fix must not open a candidate")
    }

    @Test
    func aGenuineApproachOpensACandidateAtArcZeroWellBeforeConfirmation() {
        var det = ZoneDetector(zones: [TRAKIYA_T10])
        let trace = centerlineTrace(
            TRAKIYA_T10,
            fromArcM: -200,
            metres: ZoneDetector.entryConfirmDistanceM * 2 + 200
        )

        var firstCandidateIndex = -1
        var firstCandidate: ZoneDetector.PendingEntryInfo?
        var enteredIndex = -1
        for (i, point) in trace.enumerated() {
            let state = det.update(point)
            if firstCandidate == nil, let candidate = det.pendingEntryInfo {
                firstCandidateIndex = i
                firstCandidate = candidate
                if case .outside = state {} else {
                    Issue.record("The candidate must appear while still outside — the whole point is to announce before the traversal opens, got \(state)")
                }
            }
            if enteredIndex < 0, case .inZone = state { enteredIndex = i }
        }

        let candidate = try? #require(firstCandidate)
        #expect(candidate?.zone.id == TRAKIYA_T10.id, "A car driving the road must open a candidate")
        let arc = candidate?.entryArcM ?? .infinity
        #expect(
            arc <= ZoneDetector.startWitnessArcM,
            "A genuine approach projects to arc ~0, so the announcement guard must pass it — got \(arc)m against \(ZoneDetector.startWitnessArcM)m"
        )

        // The announcement moves earlier by the whole confirmation window: the
        // candidate opens several fixes before the traversal does. Without this
        // the side channel would be pointless.
        #expect(enteredIndex > firstCandidateIndex, "The traversal must open after the candidate")
        let gainedM = Double(enteredIndex - firstCandidateIndex) * 36.0
        #expect(
            gainedM >= ZoneDetector.entryConfirmDistanceM * 0.8,
            "Announcing on the candidate must save roughly the confirmation window — expected at least \(ZoneDetector.entryConfirmDistanceM * 0.8)m, got \(gainedM)m"
        )
    }

    @Test
    func theCandidateIsClearedOnceTheTraversalOpens() {
        var det = ZoneDetector(zones: [TRAKIYA_T10])
        let states = collectAlongCenterline(
            &det, TRAKIYA_T10,
            fromArcM: -200,
            metres: ZoneDetector.entryConfirmDistanceM * 2 + 200
        )
        if case .inZone = states.last {} else {
            Issue.record("Expected a measured traversal, got \(String(describing: states.last))")
        }
        #expect(
            det.pendingEntryInfo == nil,
            "A graduated candidate must not linger — otherwise the announcement layer would see it as still pending and could re-announce"
        )
    }

    @Test
    func aRoadClippingTheBandMidZoneExposesACandidateTheArcGuardRejects() {
        // The A3 Струма / i1-02-north phantom (real drive, 2026-07-26). It is
        // `entryConfirmDistanceM` that stops it opening a traversal — but the
        // announcement no longer waits for confirmation, so the *announcement*
        // needs its own reason to stay quiet. That reason is `entryArcM`: the
        // clipping road first matches deep inside the zone, far past
        // `startWitnessArcM`, whereas a genuine approach matches at arc ~0.
        var det = ZoneDetector(zones: [TRAKIYA_T10])
        let trace = centerlineTrace(
            TRAKIYA_T10,
            fromArcM: 2_000,
            metres: ZoneDetector.entryConfirmDistanceM * 0.6,
            lateralOffsetM: 60
        )

        var candidate: ZoneDetector.PendingEntryInfo?
        for point in trace {
            let state = det.update(point)
            if case .outside = state {} else {
                Issue.record("The clipping road must never open a traversal, got \(state)")
            }
            if candidate == nil { candidate = det.pendingEntryInfo }
        }

        let seen = try? #require(candidate)
        let arc = seen?.entryArcM ?? 0
        #expect(
            arc > ZoneDetector.startWitnessArcM,
            "The phantom's first match sits deep in the zone, so the announcement guard must reject it — got \(arc)m against \(ZoneDetector.startWitnessArcM)m"
        )
    }
}
