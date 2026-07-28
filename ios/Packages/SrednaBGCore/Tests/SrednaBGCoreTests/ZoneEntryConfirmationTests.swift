// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation
import Testing
@testable import SrednaBGCore

/// Entry-side guards: a zone only opens once a match has *persisted*, and the
/// distance/average bookkeeping that goes with it. Split out of
/// `ZoneDetectorTests` to keep both files inside SwiftLint's file-length limit.
@Suite("ZoneEntryConfirmation")
struct ZoneEntryConfirmationTests {

    @Test
    func roadClippingTheBandOnAMatchingHeadingNeverOpensATraversal() {
        // Regression for the phantom I-1 traversal (real drive, 2026-07-26,
        // reproduced on both platforms). The A3 Струма motorway runs within 15 m
        // of the i1-02-north centerline for ~190 m at the Кочериново
        // interchange, on a heading inside `directionToleranceDeg`. A single
        // band-clipping fix opened a *full* traversal of the 10.6 km zone —
        // entry announcement, junk History record — that then exited seconds
        // later when the motorway pulled away.
        var det = ZoneDetector(zones: [TRAKIYA_T10])

        // A neighbouring carriageway: inside the on-road band, running parallel,
        // but only for less than the confirmation distance.
        let clip = collectAlongCenterline(
            &det, TRAKIYA_T10,
            fromArcM: 2_000,
            metres: ZoneDetector.entryConfirmDistanceM * 0.6,
            lateralOffsetM: 60
        )
        let opened = clip.first { if case .outside = $0 { return false } else { return true } }
        #expect(
            opened == nil,
            "A road clipping the band for less than entryConfirmDistanceM must never open a traversal, got \(String(describing: opened))"
        )

        // …and once it peels away the detector is still Outside, with nothing to
        // exit from (no phantom .exiting, so no History record / exit announcement).
        let away = det.update(GpsPoint(lat: 42.6, lng: 23.9, speed: 130.0, timestamp: epochBase + 60_000, bearing: 180.0))
        if case .outside = away {} else {
            Issue.record("Peeling away must stay Outside, got \(away)")
        }
    }

    @Test
    func sustainedTravelAlongTheZoneEntersBackDatedToTheFirstFix() throws {
        // The other half of the guard above: a car genuinely on the road must
        // still enter, and must not be charged for the confirmation window — the
        // traversal is back-dated to the first confirming fix, so the average
        // covers the whole drive.
        var det = ZoneDetector(zones: [TRAKIYA_T10])
        // Start on the approach road, before the entry camera: the traversal is
        // only measurable if we watched the start line being crossed.
        let states = collectAlongCenterline(
            &det, TRAKIYA_T10,
            fromArcM: -200,
            metres: ZoneDetector.entryConfirmDistanceM * 2 + 200
        )
        let entered = try #require(
            states.compactMap { state -> ZoneState.InZone? in
                if case .inZone(let inZone) = state { return inZone }
                return nil
            }.first,
            "Sustained travel along the centerline must enter the zone"
        )
        // Back-dating means the recorded entry is the first fix that *matched* the
        // zone (a couple of fixes into the approach, once we are inside the
        // on-road band), not the much later fix at which confirmation completed.
        let flipIdx = try #require(states.firstIndex { if case .inZone = $0 { return true } else { return false } })
        let stepMs = Int64(36.0 / (130.0 / 3.6) * 1000.0)
        let backDatedByMs = epochBase + Int64(flipIdx) * stepMs - entered.entryTime
        let confirmMs = Int64(ZoneDetector.entryConfirmDistanceM / (130.0 / 3.6) * 1000.0)
        #expect(Double(backDatedByMs) >= Double(confirmMs) * 0.8,
                """
                Traversal must be back-dated across the confirmation window — \
                expected at least \(Int(Double(confirmMs) * 0.8))ms, got \(backDatedByMs)ms
                """)
        #expect(entered.distanceTraveled >= ZoneDetector.entryConfirmDistanceM * 0.8,
                "Back-dated entry must carry the ground covered during confirmation, got \(entered.distanceTraveled)")
    }

    @Test
    func colocatedCameraHandsOverToTheNextZoneImmediately() throws {
        // At a co-located pair (24 in the data) one camera ends zone A and
        // begins zone B, so there is no room to re-confirm B — and no need:
        // driving A to its end IS the evidence. B must open essentially at the
        // camera, keeping the inZone(A) -> exiting(A) -> inZone(B) handover the
        // TTS layer relies on for the chained exit/entry announcement.
        let zoneA = TRAKIYA_T10
        let zoneB = nextZoneFrom(zoneA, id: "trakiya-02-west", lengthM: 6_000)
        var det = ZoneDetector(zones: [zoneA, zoneB])

        let stepM = 36.0
        let speed = 130.0
        let stepMs = Int64(stepM / (speed / 3.6) * 1000.0)
        let total = polylineLengthMeters(zoneA.centerline)

        // Drive the whole of A, from before its entry camera up to the shared one.
        // Starting mid-zone would make A unmeasured, and an unmeasured zone never
        // reaches `exitZone`, so it never offers the handover this test is about.
        let statesA = collectAlongCenterline(
            &det, zoneA, fromArcM: -200, metres: total + 200,
            speedKmh: speed, stepM: stepM
        )
        #expect(statesA.contains { if case .inZone(let z) = $0 { return z.zone.id == zoneA.id } else { return false } },
                "Should have driven zone A")
        #expect(statesA.contains { if case .exiting = $0 { return true } else { return false } },
                "Should have exited zone A at its end")

        // …then straight on into B, which starts at that same camera.
        let statesB = collectAlongCenterline(
            &det, zoneB, fromArcM: 0, metres: ZoneDetector.entryConfirmDistanceM,
            speedKmh: speed, stepM: stepM,
            startTime: epochBase + Int64(statesA.count) * stepMs
        )
        let enterBIdx = try #require(
            statesB.firstIndex { if case .inZone(let z) = $0 { return z.zone.id == zoneB.id } else { return false } },
            "Co-located zone B must open after A's exit"
        )

        // The bypass is the point: B opens well inside the distance a normal
        // confirmation would have cost, so the driver gets the new limit at the
        // camera rather than a few hundred metres past it.
        let handoverM = Double(enterBIdx) * stepM
        #expect(
            handoverM < ZoneDetector.entryConfirmDistanceM * 0.5,
            "Co-located handover took \(Int(handoverM)) m — no better than the normal \(Int(ZoneDetector.entryConfirmDistanceM)) m confirmation"
        )
    }

    @Test
    func gpsDropoutDoesNotDeflateTheReportedAverage() throws {
        // Regression for the "24 km/h" History record (real drive, 2026-07-26):
        // the integrator skipped the dropout gap while elapsed time kept counting
        // it, so ~6 s of credited distance divided by 21 s of elapsed turned an
        // ~87 km/h drive into a reported 24 km/h. Across a dropout the distance
        // is now bridged from the centerline projection.
        var det = ZoneDetector(zones: [TRAKIYA_T10])
        let speed = 90.0
        let speedMs = speed / 3.6
        let stepM = 25.0
        let stepMs = Int64(stepM / speedMs * 1000.0)
        // Approach from before the entry camera so the traversal is measurable at
        // all (see `startWitnessArcM`) — the dropout behaviour under test only
        // exists inside a measured traversal.
        let startArc = -200.0
        let drivenM = ZoneDetector.entryConfirmDistanceM * 1.5 + 200

        let states = collectAlongCenterline(
            &det, TRAKIYA_T10,
            fromArcM: startArc, metres: drivenM,
            speedKmh: speed, stepM: stepM
        )
        guard case .inZone = try #require(states.last) else {
            Issue.record("Should be in the zone before the dropout")
            return
        }
        let lastArc = startArc + Double(states.count - 1) * stepM
        let lastTime = epochBase + Int64(states.count - 1) * stepMs

        // 15 s of silence, during which the car covers 375 m of road at the same
        // steady speed.
        let dropoutMs: Int64 = 15_000
        let resumeArc = lastArc + speedMs * (Double(dropoutMs) / 1000.0)
        let resumeAt = pointAtArcLength(TRAKIYA_T10.centerline, resumeArc)
        let heading = try #require(
            localPolylineBearing(TRAKIYA_T10.centerline, resumeArc, RoadMatcher.localBearingWindowM)
        )
        let resumed = det.update(GpsPoint(
            lat: resumeAt[0], lng: resumeAt[1], speed: speed,
            timestamp: lastTime + dropoutMs, bearing: heading
        ))
        guard case .inZone(let inZone) = resumed else {
            Issue.record("Should still be in the zone after the dropout, got \(resumed)")
            return
        }

        let avg = try #require(inZone.speedStatus.avgSpeed)
        #expect(
            avg > speed * 0.85,
            "A GPS dropout must not deflate the average — driving a steady \(speed) km/h through a \(dropoutMs)ms gap reported \(avg) km/h"
        )
    }
}
