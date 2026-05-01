// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import Testing
@testable import SrednaBGTracking
import SrednaBGCore
import SrednaBGData

@Suite("AudioAlertManager")
struct AudioAlertManagerTests {

    /// Captures every TTS call so tests can assert on the phrase + language
    /// without poking the audio session.
    actor RecordingTTSEngine: TTSEngine {
        struct Call: Equatable, Sendable {
            let phrase: String
            let language: AppLanguage
        }
        private(set) var calls: [Call] = []
        private(set) var stops = 0

        func speak(_ phrase: String, language: AppLanguage) async {
            calls.append(.init(phrase: phrase, language: language))
        }
        func stop() async { stops += 1 }
    }

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

    private static func inZone(over: Bool, avg: Double? = 130) -> ZoneState {
        .inZone(.init(
            zone: zone,
            entryTime: 0,
            distanceTraveled: 0,
            avgSpeed: avg,
            speedStatus: SpeedStatus(avgSpeed: avg, maxSpeedForRemainder: 140, distanceRemaining: 0, timeRemaining: 0, isOverLimit: over),
            distanceRemaining: 0
        ))
    }

    private func snapshot(
        voice: Bool = true,
        periodic: Bool = true,
        onlyOver: Bool = true,
        vehicle: VehicleType = .car,
        lang: AppLanguage = .en
    ) -> @Sendable () async -> SettingsSnapshot {
        return {
            SettingsSnapshot(
                voiceEnabled: voice,
                periodicVoiceUpdates: periodic,
                announceOnlyWhenOver: onlyOver,
                vehicleType: vehicle,
                appLanguage: lang
            )
        }
    }

    @Test
    func entryFiresEnglishPhrase() async {
        let engine = RecordingTTSEngine()
        let mgr = AudioAlertManager(
            engine: engine,
            snapshot: snapshot(lang: .en),
            now: { Date(timeIntervalSince1970: 1_000_000) },
            deviceLanguage: { "en" }
        )
        await mgr.handle(previous: .outside, current: Self.inZone(over: false), currentSpeedKmh: 100)
        let calls = await engine.calls
        #expect(calls.count == 1)
        #expect(calls.first?.phrase == "Entering average speed zone. Speed limit 140.")
        #expect(calls.first?.language == .en)
    }

    @Test
    func entryFiresBgPhraseWhenSystemLangIsBg() async {
        let engine = RecordingTTSEngine()
        let mgr = AudioAlertManager(
            engine: engine,
            snapshot: snapshot(lang: .system),
            now: { Date(timeIntervalSince1970: 1_000_000) },
            deviceLanguage: { "bg" }
        )
        await mgr.handle(previous: .outside, current: Self.inZone(over: false), currentSpeedKmh: 100)
        let calls = await engine.calls
        #expect(calls.first?.phrase.starts(with: "Влизате") == true)
        #expect(calls.first?.language == .bg)
    }

    @Test
    func slowSpeedSuppressesAnnouncement() async {
        let engine = RecordingTTSEngine()
        let mgr = AudioAlertManager(
            engine: engine,
            snapshot: snapshot(),
            now: { Date(timeIntervalSince1970: 1_000_000) },
            deviceLanguage: { "en" }
        )
        await mgr.handle(previous: .outside, current: Self.inZone(over: false), currentSpeedKmh: 5)
        let calls = await engine.calls
        #expect(calls.isEmpty)
    }

    @Test
    func transientExitSuppressesAnnouncementButLaterExitFires() async {
        let engine = RecordingTTSEngine()
        // Use a clock we can advance between calls.
        let clock = TestClock()
        let mgr = AudioAlertManager(
            engine: engine,
            snapshot: snapshot(),
            now: { clock.read() },
            deviceLanguage: { "en" }
        )

        // T0: enter zone — entry fires, lastEntryAt = T0.
        await mgr.handle(previous: .outside, current: Self.inZone(over: false), currentSpeedKmh: 100)

        // T+2s: exit — transient (within 5s window). Suppressed.
        clock.advance(by: 2)
        await mgr.handle(
            previous: Self.inZone(over: false),
            current: .exiting(.init(zone: Self.zone, finalAvgSpeed: 130)),
            currentSpeedKmh: 100
        )
        var calls = await engine.calls
        #expect(calls.count == 1, "Only the entry should have fired so far")

        // Re-enter, then wait > 5s before exiting — exit should fire normally.
        await mgr.handle(previous: .exiting(.init(zone: Self.zone, finalAvgSpeed: nil)), current: .outside, currentSpeedKmh: 100)
        await mgr.handle(previous: .outside, current: Self.inZone(over: false), currentSpeedKmh: 100)
        clock.advance(by: 10)
        await mgr.handle(
            previous: Self.inZone(over: false),
            current: .exiting(.init(zone: Self.zone, finalAvgSpeed: 132)),
            currentSpeedKmh: 100
        )
        calls = await engine.calls
        #expect(calls.last?.phrase == "Leaving zone. Average speed was 132.")
    }

    /// Mutable date source for tests (Sendable via `OSAllocatedUnfairLock`).
    final class TestClock: @unchecked Sendable {
        private let lock = NSLock()
        private var t: TimeInterval = 1_000_000

        func read() -> Date {
            lock.withLock { Date(timeIntervalSince1970: t) }
        }

        func advance(by seconds: TimeInterval) {
            lock.withLock { t += seconds }
        }
    }
}
