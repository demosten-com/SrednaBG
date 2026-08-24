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
    // The zone whose entry was already spoken from the detector's candidate, and
    // when — see `handleProvisionalEntry`.
    private var provisionalZoneId: String?
    private var provisionalAt: Date?

    /// Set by `reset()` (tracking stopped), cleared by `resume()` (tracking
    /// started). While set, `handle` short-circuits before emitting the
    /// `speak:` log or calling the engine — so an in-flight detached `handle`
    /// task (spawned by `ZoneTrackingService.process` just before the user hit
    /// Stop) can't kick off a fresh announcement after tracking stopped.
    private var suppressed = false

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
        if suppressed { return }
        let s = await snapshot()
        // Re-check: `reset()` can interleave on this actor while we were
        // suspended awaiting the settings snapshot. If it did, drop the
        // announcement (and skip mutating the announcement clocks below).
        if suppressed { return }
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
            now: now(),
            provisionalZoneId: provisionalZoneId,
            provisionalAt: provisionalAt
        )
        let decision = AnnouncementPolicy.decide(inputs)
        // Any entry announcement retires the provisional bookkeeping: either it
        // was just consumed to suppress a duplicate, or this is a different zone
        // and the old id is stale.
        if case .inZone = current { retireProvisionalIfEntering(previous: previous) }
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
        // `followUp` (entered already over the limit) rides behind the main
        // utterance; the engine enqueues rather than clobbers, so order holds.
        // The main event can be nil while the follow-up is not: an entry already
        // announced provisionally still needs its over-limit warning.
        let spoken = [decision.event, decision.followUp].compactMap { $0 }
        guard !spoken.isEmpty else { return }
        let resolvedLang = s.appLanguage.resolvedVoiceLanguage(deviceLanguage: deviceLanguage())
        for event in spoken {
            let phrase = TtsPhrases.phrase(for: event, language: resolvedLang)
            // QA harness tripwire: line shape must match `qa/parsers.py` SPEAK_RE.
            QALog.tts.info("speak: \"\(phrase, privacy: .public)\"")
            await engine.speak(phrase, language: resolvedLang)
        }
    }

    /// Announce an entry the moment the detector opens a *candidate* for `zone`,
    /// rather than when the traversal is confirmed
    /// `ZoneDetector.entryConfirmDistanceM` later. Kotlin twin:
    /// `AudioAlertManager.onProvisionalEntry`.
    ///
    /// The measurement is untouched — a confirmed traversal is back-dated to this
    /// same candidate's first fix — so this only moves the *voice* to where the
    /// driver expects it. Before this, the entry was spoken ~300 m past the
    /// camera and the driver, who cannot know the average was back-dated, read
    /// that as the app being slow.
    ///
    /// If the candidate is later abandoned the entry simply goes unrecorded — no
    /// retraction is spoken, because a correction the driver did not ask for is
    /// more confusing than the silence.
    public func handleProvisionalEntry(zone: Zone, currentSpeedKmh: Double?) async {
        if suppressed { return }
        let s = await snapshot()
        // Re-check: `reset()` can interleave on this actor while we were
        // suspended awaiting the settings snapshot.
        if suppressed { return }
        let at = now()
        guard let event = AnnouncementPolicy.decideProvisionalEntry(
            zone: zone,
            currentSpeedKmh: currentSpeedKmh,
            voiceEnabled: s.voiceEnabled,
            vehicleType: s.vehicleType,
            provisionalZoneId: provisionalZoneId,
            provisionalAt: provisionalAt,
            now: at
        ) else { return }
        provisionalZoneId = zone.id
        provisionalAt = at
        lastEntryAt = at
        lastAnnouncementAt = at
        // QA harness tripwire: line shape must match `qa/parsers.py`
        // PROVISIONAL_SPOKEN_RE (Android twin logs the same body). `.info`, not
        // `.debug`, like every other QA line here: the unified log does not
        // persist debug messages, so `log show` cannot recover them after a run
        // — only the live stream sees them, which makes a failed run impossible
        // to diagnose after the fact.
        let speedLabel = String(format: "%.1f", currentSpeedKmh ?? 0)
        QALog.tts.info(
            "onProvisionalEntry zone=\(zone.id, privacy: .public) speed=\(speedLabel, privacy: .public)"
        )
        let resolvedLang = s.appLanguage.resolvedVoiceLanguage(deviceLanguage: deviceLanguage())
        let phrase = TtsPhrases.phrase(for: event, language: resolvedLang)
        // QA harness tripwire: line shape must match `qa/parsers.py` SPEAK_RE.
        QALog.tts.info("speak: \"\(phrase, privacy: .public)\"")
        await engine.speak(phrase, language: resolvedLang)
    }

    /// Drop the provisional bookkeeping once a traversal opens, so a stale id can
    /// never suppress a later, genuine entry into the same zone. Only the two
    /// transitions that announce an entry retire it.
    private func retireProvisionalIfEntering(previous: ZoneState) {
        switch previous {
        case .outside, .exiting:
            provisionalZoneId = nil
            provisionalAt = nil
        case .inZone, .unmeasured:
            break
        }
    }

    public func reset() async {
        suppressed = true
        lastEntryAt = nil
        lastAnnouncementAt = nil
        provisionalZoneId = nil
        provisionalAt = nil
        await engine.stop()
    }

    /// Re-arm announcements when tracking (re)starts. Counterpart to the
    /// `suppressed` flag raised by `reset()`; without this a manager reused
    /// across a stop → start cycle would stay permanently silent.
    public func resume() {
        suppressed = false
    }
}
