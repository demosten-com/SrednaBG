// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import Testing
@testable import SrednaBGData
import SrednaBGCore

@MainActor
@Suite("SettingsStore")
struct SettingsStoreTests {

    /// Each test gets its own isolated UserDefaults suite so `didSet`
    /// write-through doesn't bleed across tests.
    private func freshDefaults() -> UserDefaults {
        let suite = "SrednaBGTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        return defaults
    }

    @Test
    func defaultsMatchAndroid() {
        let store = SettingsStore(defaults: freshDefaults())
        #expect(store.alertThresholdKmh == 5)
        #expect(store.voiceEnabled == true)
        #expect(store.periodicVoiceUpdates == true)
        #expect(store.announceOnlyWhenOver == true)
        #expect(store.appLanguage == .system)
        #expect(store.vehicleType == .car)
        #expect(store.cachedZoneHash == "")
        #expect(store.cachedMapHash == "")
        #expect(store.mapHeadingUp == false)
    }

    @Test
    func mutationsPersistToUserDefaults() {
        let defaults = freshDefaults()
        let store = SettingsStore(defaults: defaults)
        store.alertThresholdKmh = 12
        store.voiceEnabled = false
        store.appLanguage = .bg
        store.vehicleType = .truck
        store.cachedZoneHash = "sha256:foo"
        store.mapHeadingUp = true

        // Hydrate a second instance from the same defaults — should see the writes.
        let reloaded = SettingsStore(defaults: defaults)
        #expect(reloaded.alertThresholdKmh == 12)
        #expect(reloaded.voiceEnabled == false)
        #expect(reloaded.appLanguage == .bg)
        #expect(reloaded.vehicleType == .truck)
        #expect(reloaded.cachedZoneHash == "sha256:foo")
        #expect(reloaded.mapHeadingUp == true)
    }

    @Test
    func keyNamesMatchAndroidByteForByte() {
        // QA harness control surface and screenshots assume the same key names
        // across Android and iOS. Don't rename without a coordinated change.
        #expect(SettingsKey.alertThresholdKmh == "alert_threshold_kmh")
        #expect(SettingsKey.voiceEnabled == "voice_enabled")
        #expect(SettingsKey.periodicVoiceUpdates == "periodic_voice_updates")
        #expect(SettingsKey.announceOnlyWhenOver == "announce_only_when_over")
        #expect(SettingsKey.appLanguage == "app_language")
        #expect(SettingsKey.vehicleType == "vehicle_type")
        #expect(SettingsKey.cachedZoneHash == "cached_zone_hash")
        #expect(SettingsKey.cachedMapHash == "cached_map_hash")
        #expect(SettingsKey.mapHeadingUp == "map_heading_up")
    }

    @Test
    func appLanguageResolvesSystemAgainstDeviceLanguage() {
        #expect(AppLanguage.system.resolvedVoiceLanguage(deviceLanguage: "bg") == .bg)
        #expect(AppLanguage.system.resolvedVoiceLanguage(deviceLanguage: "en") == .en)
        #expect(AppLanguage.system.resolvedVoiceLanguage(deviceLanguage: "fr") == .en)
        #expect(AppLanguage.bg.resolvedVoiceLanguage(deviceLanguage: "en") == .bg)
        #expect(AppLanguage.en.resolvedVoiceLanguage(deviceLanguage: "bg") == .en)
    }
}
