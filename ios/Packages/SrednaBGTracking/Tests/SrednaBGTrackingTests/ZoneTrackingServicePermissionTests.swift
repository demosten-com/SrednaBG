// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import Testing
@testable import SrednaBGTracking
import SrednaBGCore
import SrednaBGData

/// Covers the two-step authorization flow + the "refuse to start without
/// Always" gate added to `ZoneTrackingService`. The real `CLLocationTracker`
/// can't be exercised under `swift test` (no CoreLocation prompts on macOS),
/// so we drive the protocol with a scripted provider.
@Suite("ZoneTrackingService permission gate")
@MainActor
struct ZoneTrackingServicePermissionTests {

    @Test
    func startRefusesWhenAuthorizationStaysWhenInUse() async {
        // User: granted When-In-Use, declined the Always upgrade.
        let provider = ScriptedLocationProvider(
            initial: .notDetermined,
            responses: [.authorizedWhenInUse, .authorizedWhenInUse]
        )
        let service = makeService(provider: provider)

        await service.start()

        #expect(service.isTracking == false)
        #expect(service.permission == .whenInUse)
        let starts = await provider.startCount
        #expect(starts == 0, "Provider must not be started without Always")
        let prompts = await provider.requestCount
        #expect(prompts == 2, "Two-step flow issues both prompts")
    }

    @Test
    func startRefusesWhenDenied() async {
        let provider = ScriptedLocationProvider(
            initial: .notDetermined,
            responses: [.denied]
        )
        let service = makeService(provider: provider)

        await service.start()

        #expect(service.isTracking == false)
        #expect(service.permission == .denied)
        let starts = await provider.startCount
        #expect(starts == 0)
    }

    @Test
    func startProceedsWhenAlwaysGrantedDirectlyOnFirstPrompt() async {
        // Some test fixtures or future iOS revisions may grant Always on the
        // first prompt — the gate should still allow that path through.
        let provider = ScriptedLocationProvider(
            initial: .notDetermined,
            responses: [.authorizedAlways]
        )
        let service = makeService(provider: provider)

        await service.start()

        #expect(service.isTracking == true)
        #expect(service.permission == .always)
        let starts = await provider.startCount
        #expect(starts == 1)
    }

    @Test
    func startProceedsAfterTwoStepUpgrade() async {
        // Realistic iOS 13+ path: WhenInUse first, then upgrade to Always.
        let provider = ScriptedLocationProvider(
            initial: .notDetermined,
            responses: [.authorizedWhenInUse, .authorizedAlways]
        )
        let service = makeService(provider: provider)

        await service.start()

        #expect(service.isTracking == true)
        #expect(service.permission == .always)
        let prompts = await provider.requestCount
        #expect(prompts == 2)
    }

    @Test
    func startSkipsRequestsWhenAlreadyAlways() async {
        // App relaunch with previously-granted Always: no prompts should fire.
        let provider = ScriptedLocationProvider(
            initial: .authorizedAlways,
            responses: []
        )
        let service = makeService(provider: provider)

        await service.start()

        #expect(service.isTracking == true)
        #expect(service.permission == .always)
        let prompts = await provider.requestCount
        #expect(prompts == 0)
    }

    @Test
    func refreshPermissionMirrorsProviderState() async {
        let provider = ScriptedLocationProvider(
            initial: .authorizedWhenInUse,
            responses: []
        )
        let service = makeService(provider: provider)

        await service.refreshPermission()
        #expect(service.permission == .whenInUse)

        await provider.setAuthorization(.authorizedAlways)
        await service.refreshPermission()
        #expect(service.permission == .always)
    }

    // MARK: helpers

    private func makeService(provider: any LocationProviding) -> ZoneTrackingService {
        // Per-test UserDefaults suite so settings don't leak between cases.
        let suiteName = "ZoneTrackingServicePermissionTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName) ?? .standard
        let settings = SettingsStore(defaults: defaults)
        let alerts = AudioAlertManager(
            engine: NoopTTSEngine(),
            snapshot: {
                SettingsSnapshot(
                    voiceEnabled: false,
                    periodicVoiceUpdates: false,
                    announceOnlyWhenOver: true,
                    vehicleType: .car,
                    appLanguage: .en
                )
            }
        )
        return ZoneTrackingService(
            zones: [],
            provider: provider,
            alerts: alerts,
            settings: settings
        )
    }
}

/// Replays a scripted sequence of authorization responses. Each call to
/// `requestAuthorization()` consumes the next entry from `responses`. The
/// `initial` value is what the gate observes before any prompt fires.
private actor ScriptedLocationProvider: LocationProviding {

    private var current: LocationAuthorization
    private var pending: [LocationAuthorization]
    private(set) var startCount = 0
    private(set) var requestCount = 0

    init(initial: LocationAuthorization, responses: [LocationAuthorization]) {
        self.current = initial
        self.pending = responses
    }

    var authorization: LocationAuthorization { current }

    func updates() async -> AsyncStream<GpsPoint> {
        AsyncStream { _ in }
    }

    func start() async throws {
        startCount += 1
    }

    func stop() async {}

    func setIntervalMs(_ ms: Int) async {}

    func requestAuthorization() async -> LocationAuthorization {
        requestCount += 1
        guard !pending.isEmpty else { return current }
        let next = pending.removeFirst()
        current = next
        return next
    }

    func setAuthorization(_ value: LocationAuthorization) {
        current = value
    }
}

private struct NoopTTSEngine: TTSEngine {
    func speak(_ phrase: String, language: AppLanguage) async {}
    func stop() async {}
}
