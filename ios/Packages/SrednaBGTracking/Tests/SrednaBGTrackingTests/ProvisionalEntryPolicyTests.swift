// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import Testing
@testable import SrednaBGTracking
import SrednaBGCore
import SrednaBGData

/// Announcing an entry from the detector's *candidate* rather than the confirmed
/// traversal — `AnnouncementPolicy.decideProvisionalEntry` and the repeat window
/// that keeps the confirmed path from saying it twice.
///
/// Mirrors Kotlin `ProvisionalEntryGateTest`. Getting either rule wrong is silent
/// in a way no crash or lint would catch: a duplicated entry announcement, or
/// worse, a real zone driven with no announcement at all.
@Suite("ProvisionalEntryPolicy")
struct ProvisionalEntryPolicyTests {

    private static let zoneA = Zone(
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
    private static let zoneB = Zone(
        id: "trakiya-02-west",
        road: "АМ Тракия",
        roadLatin: "Trakiya",
        direction: "west",
        description: "Test",
        start: ZoneEndpoint(lat: 42.550, lng: 23.703),
        end: ZoneEndpoint(lat: 42.700, lng: 23.500),
        distanceM: 12000,
        speedLimits: SpeedLimits(car: 140, truck: 90, bus: 100, motorcycle: 140),
        centerline: [[42.550, 23.703], [42.700, 23.500]],
        source: "test",
        lastVerified: "2026-04-12"
    )

    private let base = Date(timeIntervalSince1970: 1_000_000)

    private func decide(
        zone: Zone = zoneA,
        speed: Double? = 100,
        voiceEnabled: Bool = true,
        provisionalZoneId: String? = nil,
        provisionalAt: Date? = nil,
        nowOffset: TimeInterval = 0
    ) -> AnnouncementEvent? {
        AnnouncementPolicy.decideProvisionalEntry(
            zone: zone,
            currentSpeedKmh: speed,
            voiceEnabled: voiceEnabled,
            vehicleType: .car,
            provisionalZoneId: provisionalZoneId,
            provisionalAt: provisionalAt,
            now: base.addingTimeInterval(nowOffset)
        )
    }

    @Test
    func aFreshCandidateSpeaksTheSameEntryPhraseAsTheConfirmedPath() {
        // Deliberately the same event: no second phrasing to localize, and
        // nothing signals "provisional" to the driver — from the road, we are
        // on the zone.
        #expect(decide() == .entry(road: Self.zoneA.road, limit: 140))
    }

    @Test
    func vehicleTypeStillPicksTheLimit() {
        let event = AnnouncementPolicy.decideProvisionalEntry(
            zone: Self.zoneA, currentSpeedKmh: 100, voiceEnabled: true, vehicleType: .truck,
            provisionalZoneId: nil, provisionalAt: nil, now: base
        )
        #expect(event == .entry(road: Self.zoneA.road, limit: 90))
    }

    @Test
    func mutedVoiceAndCrawlingSpeedStaySilent() {
        #expect(decide(voiceEnabled: false) == nil)
        #expect(decide(speed: 5) == nil)
        #expect(decide(speed: nil) == nil)
    }

    @Test
    func theSameZoneIsNotAnnouncedTwiceInsideTheWindow() {
        #expect(decide(provisionalZoneId: Self.zoneA.id, provisionalAt: base, nowOffset: 30) == nil)
    }

    @Test
    func aDifferentZoneIsAlwaysAnnounced() {
        #expect(decide(zone: Self.zoneB, provisionalZoneId: Self.zoneA.id, provisionalAt: base, nowOffset: 5) != nil)
    }

    @Test
    func aStaleProvisionalNeverSwallowsAGenuineLaterEntry() {
        // The failure this guards: an abandoned candidate leaves the id set with
        // nothing to clear it. Without the window, driving that same zone for
        // real an hour later would be completely silent.
        let past = AnnouncementPolicy.provisionalRepeatWindowSec + 1
        #expect(decide(provisionalZoneId: Self.zoneA.id, provisionalAt: base, nowOffset: past) != nil)
    }

    @Test
    func aConfirmedEntryAlreadySpokenProvisionallySkipsOnlyTheEntryLine() {
        // The over-limit follow-up needs a real average, which did not exist at
        // candidate time — so it must still fire from the confirmed transition
        // even though the entry line is suppressed.
        let inZone = ZoneState.inZone(ZoneState.InZone(
            zone: Self.zoneA,
            entryTime: 0,
            distanceTraveled: 4000,
            speedStatus: SpeedStatus(
                avgSpeed: 152, maxSpeedForRemainder: 120,
                distanceRemaining: 15000, timeRemaining: 400, isOverLimit: true
            ),
            distanceRemaining: 15000
        ))
        let decision = AnnouncementPolicy.decide(AnnouncementInputs(
            previousState: .outside,
            newState: inZone,
            currentSpeedKmh: 150,
            voiceEnabled: true,
            periodicEnabled: true,
            announceOnlyWhenOver: true,
            vehicleType: .car,
            lastEntryAt: nil,
            lastAnnouncementAt: nil,
            now: base.addingTimeInterval(9),
            provisionalZoneId: Self.zoneA.id,
            provisionalAt: base
        ))
        #expect(decision.event == nil, "The entry line was already spoken on the candidate")
        #expect(decision.followUp == .overLimit(avgSpeedKmh: 152))
        #expect(decision.clockUpdate == .markEntryAndAnnouncement)
    }

    @Test
    func aConfirmedEntryWithNoProvisionalStillAnnouncesNormally() {
        let inZone = ZoneState.inZone(ZoneState.InZone(
            zone: Self.zoneA,
            entryTime: 0,
            distanceTraveled: 300,
            speedStatus: SpeedStatus(
                avgSpeed: 120, maxSpeedForRemainder: 140,
                distanceRemaining: 18000, timeRemaining: 500, isOverLimit: false
            ),
            distanceRemaining: 18000
        ))
        let decision = AnnouncementPolicy.decide(AnnouncementInputs(
            previousState: .outside,
            newState: inZone,
            currentSpeedKmh: 120,
            voiceEnabled: true,
            periodicEnabled: true,
            announceOnlyWhenOver: true,
            vehicleType: .car,
            lastEntryAt: nil,
            lastAnnouncementAt: nil,
            now: base
        ))
        #expect(decision.event == .entry(road: Self.zoneA.road, limit: 140))
    }
}
