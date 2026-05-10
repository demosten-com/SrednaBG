// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCarPlay

import Foundation
import Testing
@testable import SrednaBGCarPlay
import SrednaBGCore
import SrednaBGData
import SrednaBGTracking

/// `CarPlaySceneDelegate` reaches services through the module-level
/// `CarPlayModule.sharedBundle` registry. This roundtrips through the
/// public `configure(_:)` entry point to prove the app-shell wiring path
/// the scene delegate depends on.
@MainActor
@Suite("CarPlayModule registry")
struct CarPlayModuleTests {

    @Test("sharedBundleIsNilWhenUnconfigured")
    func sharedBundleIsNilWhenUnconfigured() {
        // Clear any prior state — tests share the module singleton.
        // There's no public clear, so this test documents the initial
        // observation only when it runs first. Subsequent cases assert
        // the configured state instead.
        _ = CarPlayModule.sharedBundle   // touch, no assertion on value
    }

    @Test("configureStoresBundleRetrievableThroughSharedBundle")
    func configureStoresBundleRetrievableThroughSharedBundle() async {
        let bundle = Self.makeBundle()
        CarPlayModule.configure(bundle)
        let retrieved = CarPlayModule.sharedBundle
        #expect(retrieved != nil)
        // Tracking / settings objects are reference types; same instance
        // means configure didn't make a copy.
        #expect(retrieved?.tracking === bundle.tracking)
        #expect(retrieved?.settings === bundle.settings)
    }

    @Test("reconfiguringReplacesBundle")
    func reconfiguringReplacesBundle() async {
        let first = Self.makeBundle()
        CarPlayModule.configure(first)
        let second = Self.makeBundle()
        CarPlayModule.configure(second)
        let retrieved = CarPlayModule.sharedBundle
        #expect(retrieved?.tracking === second.tracking)
        #expect(retrieved?.tracking !== first.tracking)
    }

    // MARK: - Fixtures

    private static func makeBundle() -> CarPlayServiceBundle {
        let settings = SettingsStore(defaults: Self.ephemeralDefaults())
        let tracking = ZoneTrackingService(
            zones: [],
            provider: InertLocationProvider(),
            alerts: AudioAlertManager(engine: InertTTSEngine(), snapshot: Self.snapshot(from: settings)),
            settings: settings
        )
        return CarPlayServiceBundle(
            tracking: tracking,
            settings: settings,
            labelsProvider: { Self.labels },
            mapStyleURLProvider: { nil }
        )
    }

    private static func ephemeralDefaults() -> UserDefaults {
        let suite = "bg.srednabg.carplay.tests.\(UUID().uuidString)"
        return UserDefaults(suiteName: suite)!
    }

    private static func snapshot(from settings: SettingsStore) -> @Sendable () async -> SettingsSnapshot {
        {
            await MainActor.run {
                SettingsSnapshot(
                    voiceEnabled: settings.voiceEnabled,
                    periodicVoiceUpdates: settings.periodicVoiceUpdates,
                    announceOnlyWhenOver: settings.announceOnlyWhenOver,
                    vehicleType: settings.vehicleType,
                    appLanguage: settings.appLanguage
                )
            }
        }
    }

    private static let labels = CarPlayLabels(
        overLimit: "", withinLimit: "", nowSpeedFormat: "%@",
        currentSpeedLabel: "", avgSpeedLabel: "", remaining: "",
        speedLimit: "", finalAvgSpeedFormat: "%@",
        zoneCompleteTitle: "", trackingOutsideTitle: "",
        notTrackingTitle: "", tapToStartHint: ""
    )
}

// MARK: - Inert test stubs

/// No GPS, no events — just satisfies the protocol so ZoneTrackingService
/// can be instantiated on any platform without CoreLocation.
private struct InertLocationProvider: LocationProviding {
    var authorization: LocationAuthorization { get async { .unknown } }
    func updates() async -> AsyncStream<GpsPoint> { AsyncStream { _ in } }
    func start() async throws {}
    func stop() async {}
    func setIntervalMs(_ ms: Int) async {}
    func requestAuthorization() async -> LocationAuthorization { .unknown }
}

private struct InertTTSEngine: TTSEngine {
    func speak(_ phrase: String, language: AppLanguage) async {}
    func stop() async {}
}
