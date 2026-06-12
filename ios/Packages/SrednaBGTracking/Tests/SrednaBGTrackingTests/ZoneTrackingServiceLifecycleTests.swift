// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import Testing
@testable import SrednaBGTracking
import SrednaBGCore
import SrednaBGData

/// Covers two lifecycle invariants of `ZoneTrackingService`:
///   * `updateZones` replaces the catalog on *content* changes, not just ID
///     changes — the sync path is hash-gated upstream, so a zone whose limit
///     moved under a stable ID must still reach the running detector.
///   * `start()` is reentrancy-safe — the method suspends before `isTracking`
///     flips, and a second concurrent call must not start a second session.
@Suite("ZoneTrackingService lifecycle")
@MainActor
struct ZoneTrackingServiceLifecycleTests {

    @Test
    func updateZonesAppliesContentOnlyChange() {
        let zone = Self.makeZone(carLimit: 140)
        let service = makeService(provider: SlowAlwaysProvider(), zones: [zone])

        // Same ID, changed speed limit — must replace the catalog.
        let edited = Self.makeZone(carLimit: 120)
        service.updateZones([edited])

        #expect(service.zones == [edited])
        #expect(service.zones.first?.speedLimits.car == 120)
    }

    @Test
    func updateZonesIgnoresIdenticalCatalog() {
        let zone = Self.makeZone(carLimit: 140)
        let service = makeService(provider: SlowAlwaysProvider(), zones: [zone])

        service.updateZones([zone])

        #expect(service.zones == [zone])
    }

    @Test
    func concurrentStartsBeginOnlyOneSession() async {
        let provider = SlowAlwaysProvider()
        let service = makeService(provider: provider, zones: [])

        // Both calls run on the MainActor; the first suspends at the provider
        // hop, letting the second interleave — the isStarting guard must turn
        // it away.
        async let first: Void = service.start()
        async let second: Void = service.start()
        _ = await (first, second)

        #expect(service.isTracking)
        let starts = await provider.startCount
        #expect(starts == 1, "Second start() must not begin a second session")

        await service.stop()
        #expect(!service.isTracking)
    }

    // MARK: helpers

    private static func makeZone(carLimit: Int) -> Zone {
        Zone(
            id: "trakiya-01-west",
            road: "АМ Тракия",
            direction: "west",
            description: "Test",
            start: ZoneEndpoint(lat: 42.427, lng: 23.855),
            end: ZoneEndpoint(lat: 42.550, lng: 23.703),
            distanceM: 19_160,
            speedLimits: SpeedLimits(car: carLimit, truck: 90, bus: 100),
            centerline: [[42.427, 23.855], [42.550, 23.703]],
            source: "test",
            lastVerified: "2026-04-12"
        )
    }

    private func makeService(provider: any LocationProviding, zones: [Zone]) -> ZoneTrackingService {
        let suiteName = "ZoneTrackingServiceLifecycleTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName) ?? .standard
        let settings = SettingsStore(defaults: defaults)
        let alerts = AudioAlertManager(
            engine: NoopLifecycleTTSEngine(),
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
            zones: zones,
            provider: provider,
            alerts: alerts,
            settings: settings
        )
    }
}

/// Always-authorized provider whose async hops yield, so a second `start()`
/// call gets a chance to interleave on the MainActor mid-flow.
private actor SlowAlwaysProvider: LocationProviding {

    private(set) var startCount = 0

    var authorization: LocationAuthorization {
        get async {
            await Task.yield()
            return .authorizedAlways
        }
    }

    func updates() async -> AsyncStream<GpsPoint> {
        AsyncStream { _ in }
    }

    func start() async throws {
        await Task.yield()
        startCount += 1
    }

    func stop() async {}

    func setIntervalMs(_ ms: Int) async {}

    func requestAuthorization() async -> LocationAuthorization { .authorizedAlways }
}

private struct NoopLifecycleTTSEngine: TTSEngine {
    func speak(_ phrase: String, language: AppLanguage) async {}
    func stop() async {}
}
