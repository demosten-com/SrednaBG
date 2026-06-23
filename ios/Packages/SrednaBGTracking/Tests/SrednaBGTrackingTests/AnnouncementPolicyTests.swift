// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import Testing
@testable import SrednaBGTracking
import SrednaBGCore
import SrednaBGData

@Suite("AnnouncementPolicy")
struct AnnouncementPolicyTests {

    private static let zone = Zone(
        id: "trakiya-01-west",
        road: "АМ Тракия",
        roadLatin: "Trakiya",
        direction: "west",
        description: "Test",
        start: ZoneEndpoint(lat: 42.427, lng: 23.855),
        end: ZoneEndpoint(lat: 42.550, lng: 23.703),
        distanceM: 19160,
        speedLimits: SpeedLimits(car: 140, truck: 90, bus: 100, motorcycle: 140),
        centerline: [[42.427, 23.855], [42.550, 23.703]],
        source: "test",
        lastVerified: "2026-04-12"
    )

    private func inZone(over: Bool, avgSpeed: Double? = 130) -> ZoneState {
        .inZone(.init(
            zone: Self.zone,
            entryTime: 0,
            distanceTraveled: 0,
            speedStatus: SpeedStatus(
                avgSpeed: avgSpeed,
                maxSpeedForRemainder: 140,
                distanceRemaining: 0,
                timeRemaining: 0,
                isOverLimit: over
            ),
            distanceRemaining: 0
        ))
    }

    private func exiting(finalAvg: Double?) -> ZoneState {
        .exiting(.init(zone: Self.zone, finalAvgSpeed: finalAvg))
    }

    private static let zoneB = Zone(
        id: "trakiya-02-west",
        road: "АМ Тракия (Б)",
        roadLatin: "Trakiya B",
        direction: "west",
        description: "Test B",
        start: ZoneEndpoint(lat: 42.550, lng: 23.703),
        end: ZoneEndpoint(lat: 42.650, lng: 23.600),
        distanceM: 15000,
        speedLimits: SpeedLimits(car: 120, truck: 80, bus: 100, motorcycle: 120),
        centerline: [[42.550, 23.703], [42.650, 23.600]],
        source: "test",
        lastVerified: "2026-04-12"
    )

    private func exitingZone(_ zone: Zone) -> ZoneState {
        .exiting(.init(zone: zone, finalAvgSpeed: 130))
    }

    private func inZone(_ zone: Zone) -> ZoneState {
        .inZone(.init(
            zone: zone,
            entryTime: 0,
            distanceTraveled: 0,
            speedStatus: SpeedStatus(
                avgSpeed: 130,
                maxSpeedForRemainder: 140,
                distanceRemaining: 0,
                timeRemaining: 0,
                isOverLimit: false
            ),
            distanceRemaining: 0
        ))
    }

    private func inputs(
        prev: ZoneState,
        new: ZoneState,
        speed: Double? = 100,
        voiceEnabled: Bool = true,
        periodic: Bool = true,
        onlyOver: Bool = true,
        vehicle: VehicleType = .car,
        lastEntry: Date? = nil,
        lastAnn: Date? = nil,
        nowOffset: TimeInterval = 0
    ) -> AnnouncementInputs {
        AnnouncementInputs(
            previousState: prev,
            newState: new,
            currentSpeedKmh: speed,
            voiceEnabled: voiceEnabled,
            periodicEnabled: periodic,
            announceOnlyWhenOver: onlyOver,
            vehicleType: vehicle,
            lastEntryAt: lastEntry,
            lastAnnouncementAt: lastAnn,
            now: Date(timeIntervalSince1970: 1_000_000 + nowOffset)
        )
    }

    @Test
    func voiceMutedSuppressesEverything() {
        let d = AnnouncementPolicy.decide(inputs(
            prev: .outside, new: inZone(over: false),
            voiceEnabled: false
        ))
        #expect(d.event == nil)
        #expect(d.clockUpdate == .none)
    }

    @Test
    func slowSpeedSuppressesEverything() {
        // Just under the 10 km/h floor — driver isn't actually moving.
        let d = AnnouncementPolicy.decide(inputs(
            prev: .outside, new: inZone(over: false), speed: 5
        ))
        #expect(d.event == nil)
    }

    @Test
    func entryAnnouncesWithCarLimit() {
        let d = AnnouncementPolicy.decide(inputs(
            prev: .outside, new: inZone(over: false), vehicle: .car
        ))
        #expect(d.event == .entry(road: "АМ Тракия", limit: 140))
        #expect(d.clockUpdate == .markEntryAndAnnouncement)
    }

    @Test
    func entryAnnouncesWithTruckLimit() {
        // iOS bug-fix: vehicle-aware limit. Truck on a 140 km/h motorway gets 90.
        let d = AnnouncementPolicy.decide(inputs(
            prev: .outside, new: inZone(over: false), vehicle: .truck
        ))
        #expect(d.event == .entry(road: "АМ Тракия", limit: 90))
    }

    @Test
    func transitionToOverFiresOverLimit() {
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: false), new: inZone(over: true, avgSpeed: 152)
        ))
        #expect(d.event == .overLimit(avgSpeedKmh: 152))
        #expect(d.clockUpdate == .markAnnouncement)
    }

    @Test
    func transitionToWithinFiresRecovered() {
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: true), new: inZone(over: false, avgSpeed: 138)
        ))
        #expect(d.event == .recovered(avgSpeedKmh: 138))
    }

    @Test
    func periodicWithinLimitSuppressedWhenOnlyOverFlagSet() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let lastAnn = now.addingTimeInterval(-31) // > 30s ago
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: false), new: inZone(over: false, avgSpeed: 130),
            periodic: true, onlyOver: true,
            lastAnn: lastAnn
        ))
        #expect(d.event == nil)
        // Critical: do NOT bump lastAnnouncementAt — next overspeed must fire immediately.
        #expect(d.clockUpdate == .none)
    }

    @Test
    func periodicWithinLimitFiresWhenOnlyOverFlagOff() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let lastAnn = now.addingTimeInterval(-31)
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: false), new: inZone(over: false, avgSpeed: 130),
            periodic: true, onlyOver: false,
            lastAnn: lastAnn
        ))
        #expect(d.event == .withinLimit(avgSpeedKmh: 130))
    }

    @Test
    func periodicOverLimitFiresEveryThirtySecondsRegardlessOfFlag() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let lastAnn = now.addingTimeInterval(-31)
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: true), new: inZone(over: true, avgSpeed: 152),
            periodic: true, onlyOver: true,
            lastAnn: lastAnn
        ))
        #expect(d.event == .overLimit(avgSpeedKmh: 152))
    }

    @Test
    func periodicSkippedWhenWindowNotElapsed() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let lastAnn = now.addingTimeInterval(-10) // only 10s ago
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: false), new: inZone(over: false, avgSpeed: 130),
            periodic: true, onlyOver: false,
            lastAnn: lastAnn
        ))
        #expect(d.event == nil)
    }

    @Test
    func periodicDisabledSkipsSteadyState() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let lastAnn = now.addingTimeInterval(-60)
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: false), new: inZone(over: false, avgSpeed: 130),
            periodic: false, onlyOver: false,
            lastAnn: lastAnn
        ))
        #expect(d.event == nil)
    }

    @Test
    func transientExitSuppressesAnnouncement() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        // Exited 2s after entry — looks like a GPS glitch.
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: false), new: exiting(finalAvg: 130),
            lastEntry: now.addingTimeInterval(-2)
        ))
        #expect(d.event == nil)
        #expect(d.clockUpdate == .clearAnnouncement)
    }

    @Test
    func realExitAnnouncesFinalAverage() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: false), new: exiting(finalAvg: 132),
            lastEntry: now.addingTimeInterval(-300) // 5 min ago
        ))
        #expect(d.event == .exit(avgSpeedKmh: 132))
        #expect(d.clockUpdate == .clearAnnouncement)
    }

    @Test
    func exitWithoutFinalAverageStaysSilent() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let d = AnnouncementPolicy.decide(inputs(
            prev: inZone(over: false), new: exiting(finalAvg: nil),
            lastEntry: now.addingTimeInterval(-300)
        ))
        #expect(d.event == nil)
    }

    @Test
    func coLocatedEntryAnnounced() {
        // Co-located cameras: A ends and B begins on consecutive fixes
        // (Exiting(A) → InZone(B), no Outside between). Entering B must announce.
        let d = AnnouncementPolicy.decide(inputs(
            prev: exitingZone(Self.zone), new: inZone(Self.zoneB)
        ))
        #expect(d.event == .entry(road: "АМ Тракия (Б)", limit: 120))
        #expect(d.clockUpdate == .markEntryAndAnnouncement)
    }

    @Test
    func coLocatedSameZoneReadmitSilent() {
        // Same-zone re-admission (off-road blip / hooked-tail flap recovered) is
        // NOT a new zone — stay silent.
        let d = AnnouncementPolicy.decide(inputs(
            prev: exitingZone(Self.zone), new: inZone(Self.zone)
        ))
        #expect(d.event == nil)
        #expect(d.clockUpdate == .none)
    }
}
