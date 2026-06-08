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
        now: Date
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
    }
}

/// Outcome of `AnnouncementPolicy.decide`. The orchestrator interprets the
/// `clockUpdate` to update its retained timestamps before issuing TTS.
public struct AnnouncementDecision: Sendable, Equatable {
    public let event: AnnouncementEvent?
    public let clockUpdate: ClockUpdate

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

        switch (input.previousState, input.newState) {

        // Outside → InZone: always announce entry.
        case (.outside, .inZone(let inZone)):
            let limit = input.vehicleType.limit(inZone.zone.speedLimits)
            return .init(
                event: .entry(road: inZone.zone.road, limit: limit),
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
                clockUpdate: .markEntryAndAnnouncement
            )

        default:
            return .silent
        }
    }
}

private extension AnnouncementDecision {
    static let silent = AnnouncementDecision(event: nil, clockUpdate: .none)
}
