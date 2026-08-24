// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import SrednaBGCore
import SrednaBGData

/// Pure decision function: given a zone-state transition + relevant settings +
/// "now" + the last-announcement clock, return the optional event the
/// orchestrator should hand to the TTS engine.
///
/// Mirrors the branching in `AudioAlertManager.onZoneStateChanged` in
/// `android/.../service/AudioAlertManager.kt`. Designed pure so the entire
/// behavior matrix is unit-testable.
public struct AnnouncementInputs: Sendable, Equatable {
    public var previousState: ZoneState
    public var newState: ZoneState
    public var currentSpeedKmh: Double?
    public var voiceEnabled: Bool
    public var periodicEnabled: Bool
    public var announceOnlyWhenOver: Bool
    public var vehicleType: VehicleType
    public var lastEntryAt: Date?
    public var lastAnnouncementAt: Date?
    public var now: Date
    /// The zone whose entry was already spoken from the detector's *candidate*,
    /// before the traversal confirmed — see `AudioAlertManager.handleProvisionalEntry`.
    /// When the confirmed `.outside -> .inZone` transition for that same zone
    /// then arrives, the entry line is skipped rather than repeated.
    public var provisionalZoneId: String?
    public var provisionalAt: Date?

    public init(
        previousState: ZoneState,
        newState: ZoneState,
        currentSpeedKmh: Double?,
        voiceEnabled: Bool,
        periodicEnabled: Bool,
        announceOnlyWhenOver: Bool,
        vehicleType: VehicleType,
        lastEntryAt: Date?,
        lastAnnouncementAt: Date?,
        now: Date,
        provisionalZoneId: String? = nil,
        provisionalAt: Date? = nil
    ) {
        self.previousState = previousState
        self.newState = newState
        self.currentSpeedKmh = currentSpeedKmh
        self.voiceEnabled = voiceEnabled
        self.periodicEnabled = periodicEnabled
        self.announceOnlyWhenOver = announceOnlyWhenOver
        self.vehicleType = vehicleType
        self.lastEntryAt = lastEntryAt
        self.lastAnnouncementAt = lastAnnouncementAt
        self.now = now
        self.provisionalZoneId = provisionalZoneId
        self.provisionalAt = provisionalAt
    }
}

/// Outcome of `AnnouncementPolicy.decide`. The orchestrator interprets the
/// `clockUpdate` to update its retained timestamps before issuing TTS.
public struct AnnouncementDecision: Sendable, Equatable {
    public let event: AnnouncementEvent?
    /// A second utterance to queue *after* `event`, when one transition warrants
    /// two things being said. Only used for "entered a zone already over the
    /// limit" — see the `(.outside, .inZone)` case in `decide`. `AVSpeechSynthesizer`
    /// enqueues rather than clobbers, so speaking both in order needs no extra
    /// coordination (Android has to pass QUEUE_ADD explicitly).
    public let followUp: AnnouncementEvent?
    public let clockUpdate: ClockUpdate

    public init(
        event: AnnouncementEvent?,
        followUp: AnnouncementEvent? = nil,
        clockUpdate: ClockUpdate
    ) {
        self.event = event
        self.followUp = followUp
        self.clockUpdate = clockUpdate
    }

    public enum ClockUpdate: Sendable, Equatable {
        case none
        case markEntryAndAnnouncement
        case markAnnouncement
        case clearAnnouncement
    }
}

public enum AnnouncementPolicy {
    public static let minAnnounceSpeedKmh = 10.0
    public static let transientExitWindowSec = 5.0
    public static let periodicIntervalSec = 30.0

    public static func decide(_ input: AnnouncementInputs) -> AnnouncementDecision {
        // Master mute + slow-vehicle filter (don't shout at someone idling on the shoulder).
        guard input.voiceEnabled else { return .silent }
        guard (input.currentSpeedKmh ?? 0) >= minAnnounceSpeedKmh else { return .silent }

        // Every transition into or out of `.unmeasured` is silent, and that is a
        // decision rather than a pair falling through to the `default` below. We
        // never saw the entry camera, so there is no entry to announce, no average
        // to warn about and no exit to sum up — saying anything would imply we are
        // measuring. Checked before the pair switch so no later case can claim one
        // of these transitions. Mirrors `AudioAlertManager.onZoneStateChanged` on
        // Android.
        //
        // "First" is about the pair switch only — it is not coupled to the speed
        // guard above. A stopped driver is already silent by suppression, so
        // neither moving that guard below this check nor moving this check below
        // it would break the contract; the silence holds either way. Pinned by
        // `AnnouncementPolicyTests.everyUnmeasuredTransitionIsSilent`, which
        // drives every pair at 100 km/h so the speed guard can't be what passes it.
        if case .unmeasured = input.previousState { return .silent }
        if case .unmeasured = input.newState { return .silent }

        switch (input.previousState, input.newState) {

        // Outside → InZone: always announce entry, plus an immediate over-limit
        // warning when the traversal *opens* already over.
        //
        // The (.inZone, .inZone) branch below only reacts to a false→true flip in
        // isOverLimit, which assumed a traversal always starts at ~0 average and
        // climbs. That stopped being true once entry gained a confirmation window
        // (ZoneDetector.entryConfirmDistanceM) that is back-dated to the first
        // confirming fix: the first .inZone state now carries a few hundred metres
        // of real driving, so a driver who was already speeding enters *over* the
        // limit and there is no flip left to react to. Mirrors
        // `AudioAlertManager.announceEntryOverLimit` on Android; regression
        // `qa/scenarios/edge/vehicle_type_limit_badge.py`.
        case (.outside, .inZone(let inZone)):
            let limit = input.vehicleType.limit(inZone.zone.speedLimits)
            // Already spoken when the candidate opened, a few hundred metres
            // back. Skip only the entry line: the over-limit follow-up needs a
            // real average, which did not exist at candidate time, so it must
            // still fire from this confirmed transition.
            let alreadySpoken = isProvisionalStillFresh(
                zoneId: inZone.zone.id,
                provisionalZoneId: input.provisionalZoneId,
                provisionalAt: input.provisionalAt,
                now: input.now
            )
            return .init(
                event: alreadySpoken ? nil : .entry(road: inZone.zone.road, limit: limit),
                followUp: entryOverLimitEvent(inZone),
                clockUpdate: .markEntryAndAnnouncement
            )

        // Within zone: handle over/under transitions + periodic ticks.
        case (.inZone(let prev), .inZone(let new)):
            guard let avgSpeed = new.avgSpeed.map({ Int($0) }) else { return .silent }
            let isOver = new.speedStatus.isOverLimit
            let wasOver = prev.speedStatus.isOverLimit

            if !wasOver && isOver {
                return .init(event: .overLimit(avgSpeedKmh: avgSpeed), clockUpdate: .markAnnouncement)
            }
            if wasOver && !isOver {
                return .init(event: .recovered(avgSpeedKmh: avgSpeed), clockUpdate: .markAnnouncement)
            }
            // Steady state — periodic announcement?
            guard input.periodicEnabled else { return .silent }
            let last = input.lastAnnouncementAt ?? .distantPast
            let elapsed = input.now.timeIntervalSince(last)
            guard elapsed > periodicIntervalSec else { return .silent }

            if isOver {
                return .init(event: .overLimit(avgSpeedKmh: avgSpeed), clockUpdate: .markAnnouncement)
            }
            if input.announceOnlyWhenOver {
                // Suppressed; do NOT touch lastAnnouncementAt so the next
                // over-limit tick can fire without another 30s wait. Mirrors
                // the explicit Android comment block.
                return .silent
            }
            return .init(event: .withinLimit(avgSpeedKmh: avgSpeed), clockUpdate: .markAnnouncement)

        // InZone → Exiting: announce exit unless this is a transient glitch.
        case (.inZone, .exiting(let exiting)):
            if let entry = input.lastEntryAt,
               input.now.timeIntervalSince(entry) < transientExitWindowSec {
                return .init(event: nil, clockUpdate: .clearAnnouncement)
            }
            guard let avg = exiting.finalAvgSpeed.map({ Int($0) }) else { return .silent }
            return .init(event: .exit(avgSpeedKmh: avg), clockUpdate: .clearAnnouncement)

        // Co-located cameras: one camera ends zone A and begins zone B, so the
        // state machine steps InZone(A) → Exiting(A) → InZone(B) on consecutive
        // fixes with no Outside between them. The exit-with-average for A already
        // announced on the prior InZone → Exiting transition; here we must
        // announce ENTERING B — without this branch the next-zone entry is silent.
        // Mirrors `AudioAlertManager.kt`'s `Exiting → InZone` branch. (No queueing
        // needed as on Android: `AVSpeechSynthesizer` enqueues utterances and only
        // releases the audio session when the queue drains, so B's entry plays
        // after A's still-speaking exit line on its own.)
        case (.exiting(let prev), .inZone(let new)):
            // Same zone re-admitted (off-road blip / hooked-tail flap recovered),
            // not a new zone — no entry announcement.
            if prev.zone.id == new.zone.id { return .silent }
            let limit = input.vehicleType.limit(new.zone.speedLimits)
            return .init(
                event: .entry(road: new.zone.road, limit: limit),
                followUp: entryOverLimitEvent(new),
                clockUpdate: .markEntryAndAnnouncement
            )

        default:
            return .silent
        }
    }

    /// How long a spoken provisional entry suppresses another one for the same
    /// zone. Kotlin twin: `PROVISIONAL_REPEAT_WINDOW_MS`.
    ///
    /// A candidate that goes quiet for `ZoneDetector.entryConfirmTimeoutMs`
    /// (30 s) and then re-opens is a brand-new candidate as far as the detector
    /// is concerned, but the driver does not need to hear the same zone
    /// announced twice inside a minute.
    public static let provisionalRepeatWindowSec = 60.0

    /// Should this fix speak an entry for a zone the detector has only opened a
    /// *candidate* for, `ZoneDetector.entryConfirmDistanceM` before the
    /// traversal will confirm?
    ///
    /// The caller has already applied the `startWitnessArcM` guard on the
    /// candidate's arc (see `ZoneTrackingService`); this owns the voice-enabled,
    /// speed and repeat rules, so they cannot drift from the confirmed path's.
    /// Kotlin twin: `AudioAlertManager.onProvisionalEntry`.
    public static func decideProvisionalEntry(
        zone: Zone,
        currentSpeedKmh: Double?,
        voiceEnabled: Bool,
        vehicleType: VehicleType,
        provisionalZoneId: String?,
        provisionalAt: Date?,
        now: Date
    ) -> AnnouncementEvent? {
        guard voiceEnabled else { return nil }
        guard (currentSpeedKmh ?? 0) >= minAnnounceSpeedKmh else { return nil }
        guard !isProvisionalStillFresh(
            zoneId: zone.id, provisionalZoneId: provisionalZoneId,
            provisionalAt: provisionalAt, now: now
        ) else { return nil }
        // Deliberately the *same* event as the confirmed path: no second
        // phrasing to localize, and nothing signals "provisional" to the driver
        // — from the road, we are on the zone.
        return .entry(road: zone.road, limit: vehicleType.limit(zone.speedLimits))
    }

    /// Has `zoneId` already been announced provisionally, recently enough that
    /// the driver still remembers hearing it? Kotlin twin:
    /// `isProvisionalStillFresh`.
    ///
    /// The recency clause is not decoration. A candidate that is announced and
    /// then abandoned leaves the id set with nothing to clear it, so without the
    /// window a genuine entry into that same zone half an hour later would be
    /// silently swallowed — the driver would drive a real zone with no
    /// announcement at all. Bounding both callers by the same window keeps them
    /// in agreement: inside it the driver has heard this zone (whether or not a
    /// repeat was suppressed), outside it they have not.
    public static func isProvisionalStillFresh(
        zoneId: String,
        provisionalZoneId: String?,
        provisionalAt: Date?,
        now: Date,
        windowSec: Double = provisionalRepeatWindowSec
    ) -> Bool {
        guard zoneId == provisionalZoneId, let at = provisionalAt else { return false }
        return now.timeIntervalSince(at) < windowSec
    }

    /// The over-limit warning to queue behind an entry announcement, when the
    /// traversal opens already over the limit. Nil otherwise.
    private static func entryOverLimitEvent(_ inZone: ZoneState.InZone) -> AnnouncementEvent? {
        guard inZone.speedStatus.isOverLimit, let avg = inZone.avgSpeed.map({ Int($0) })
        else { return nil }
        return .overLimit(avgSpeedKmh: avg)
    }
}

private extension AnnouncementDecision {
    static let silent = AnnouncementDecision(event: nil, clockUpdate: .none)
}
