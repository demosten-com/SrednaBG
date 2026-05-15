// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import SrednaBGCore
import SrednaBGData

/// Snapshot of the four `SettingsStore` knobs the announcement policy needs.
/// Pulled into a value type so `AudioAlertManager` can re-read settings per
/// transition without taking an actor hop on `SettingsStore`.
public struct SettingsSnapshot: Sendable, Equatable {
    public let voiceEnabled: Bool
    public let periodicVoiceUpdates: Bool
    public let announceOnlyWhenOver: Bool
    public let vehicleType: VehicleType
    public let appLanguage: AppLanguage

    public init(
        voiceEnabled: Bool,
        periodicVoiceUpdates: Bool,
        announceOnlyWhenOver: Bool,
        vehicleType: VehicleType,
        appLanguage: AppLanguage
    ) {
        self.voiceEnabled = voiceEnabled
        self.periodicVoiceUpdates = periodicVoiceUpdates
        self.announceOnlyWhenOver = announceOnlyWhenOver
        self.vehicleType = vehicleType
        self.appLanguage = appLanguage
    }
}

/// Owns the announcement state machine. Receives `ZoneState` transitions from
/// `ZoneTrackingService`, consults `AnnouncementPolicy`, and forwards the
/// resulting phrase to the injected `TTSEngine`.
///
/// Actor-isolated so concurrent transitions (e.g. a settings change racing a
/// zone entry) can't tear the `AnnouncementState`. The `now` and `snapshot`
/// closures are injected so tests can drive every branch with a fake clock.
public actor AudioAlertManager {

    private let engine: any TTSEngine
    private let snapshot: @Sendable () async -> SettingsSnapshot
    private let now: @Sendable () -> Date
    private let deviceLanguage: @Sendable () -> String

    private var lastEntryAt: Date?
    private var lastAnnouncementAt: Date?

    public init(
        engine: any TTSEngine,
        snapshot: @escaping @Sendable () async -> SettingsSnapshot,
        now: @escaping @Sendable () -> Date = { Date() },
        deviceLanguage: @escaping @Sendable () -> String = { Locale.current.language.languageCode?.identifier ?? "en" }
    ) {
        self.engine = engine
        self.snapshot = snapshot
        self.now = now
        self.deviceLanguage = deviceLanguage
    }

    public func handle(previous: ZoneState, current: ZoneState, currentSpeedKmh: Double?) async {
        let s = await snapshot()
        let inputs = AnnouncementInputs(
            previousState: previous,
            newState: current,
            currentSpeedKmh: currentSpeedKmh,
            voiceEnabled: s.voiceEnabled,
            periodicEnabled: s.periodicVoiceUpdates,
            announceOnlyWhenOver: s.announceOnlyWhenOver,
            vehicleType: s.vehicleType,
            lastEntryAt: lastEntryAt,
            lastAnnouncementAt: lastAnnouncementAt,
            now: now()
        )
        let decision = AnnouncementPolicy.decide(inputs)
        switch decision.clockUpdate {
        case .none: break
        case .markEntryAndAnnouncement:
            lastEntryAt = inputs.now
            lastAnnouncementAt = inputs.now
        case .markAnnouncement:
            lastAnnouncementAt = inputs.now
        case .clearAnnouncement:
            lastAnnouncementAt = nil
        }
        guard let event = decision.event else { return }
        let resolvedLang = s.appLanguage.resolvedVoiceLanguage(deviceLanguage: deviceLanguage())
        let phrase = TtsPhrases.phrase(for: event, language: resolvedLang)
        // QA harness tripwire: line shape must match `qa/parsers.py` SPEAK_RE.
        QALog.tts.info("speak: \"\(phrase, privacy: .public)\"")
        await engine.speak(phrase, language: resolvedLang)
    }

    public func reset() async {
        lastEntryAt = nil
        lastAnnouncementAt = nil
        await engine.stop()
    }
}
