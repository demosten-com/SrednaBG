// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import Observation
import SrednaBGCore

/// `@Observable` wrapper around `UserDefaults`. SwiftUI views bind to its
/// stored properties; `didSet` writes through to disk so a settings flip
/// survives a process restart and is visible to the QA harness's
/// `DebugControlReceiver` analogue (a future debug-only `URL` handler).
///
/// Eight settings keys, mirroring `SettingsRepository.kt` byte-identically.
@Observable
@MainActor
public final class SettingsStore {

    @ObservationIgnored
    private let defaults: UserDefaults

    public var alertThresholdKmh: Int {
        didSet { defaults.set(alertThresholdKmh, forKey: SettingsKey.alertThresholdKmh) }
    }

    public var voiceEnabled: Bool {
        didSet { defaults.set(voiceEnabled, forKey: SettingsKey.voiceEnabled) }
    }

    public var periodicVoiceUpdates: Bool {
        didSet { defaults.set(periodicVoiceUpdates, forKey: SettingsKey.periodicVoiceUpdates) }
    }

    public var announceOnlyWhenOver: Bool {
        didSet { defaults.set(announceOnlyWhenOver, forKey: SettingsKey.announceOnlyWhenOver) }
    }

    public var appLanguage: AppLanguage {
        didSet { defaults.set(appLanguage.rawValue, forKey: SettingsKey.appLanguage) }
    }

    public var vehicleType: VehicleType {
        didSet { defaults.set(vehicleType.rawValue, forKey: SettingsKey.vehicleType) }
    }

    public var cachedZoneHash: String {
        didSet { defaults.set(cachedZoneHash, forKey: SettingsKey.cachedZoneHash) }
    }

    public var cachedMapHash: String {
        didSet { defaults.set(cachedMapHash, forKey: SettingsKey.cachedMapHash) }
    }

    public var mapHeadingUp: Bool {
        didSet { defaults.set(mapHeadingUp, forKey: SettingsKey.mapHeadingUp) }
    }

    public var mapThemeMode: MapThemeMode {
        didSet { defaults.set(mapThemeMode.rawValue, forKey: SettingsKey.mapThemeMode) }
    }

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults

        // Initial reads bypass `didSet` (Swift does not invoke property observers
        // during `init`), so this hydration does not loop back into UserDefaults.
        self.alertThresholdKmh = (defaults.object(forKey: SettingsKey.alertThresholdKmh) as? Int)
            ?? SettingsDefaults.alertThresholdKmh
        self.voiceEnabled = (defaults.object(forKey: SettingsKey.voiceEnabled) as? Bool)
            ?? SettingsDefaults.voiceEnabled
        self.periodicVoiceUpdates = (defaults.object(forKey: SettingsKey.periodicVoiceUpdates) as? Bool)
            ?? SettingsDefaults.periodicVoiceUpdates
        self.announceOnlyWhenOver = (defaults.object(forKey: SettingsKey.announceOnlyWhenOver) as? Bool)
            ?? SettingsDefaults.announceOnlyWhenOver
        self.appLanguage = (defaults.string(forKey: SettingsKey.appLanguage)).flatMap(AppLanguage.init(rawValue:))
            ?? SettingsDefaults.appLanguage
        self.vehicleType = (defaults.string(forKey: SettingsKey.vehicleType)).flatMap(VehicleType.init(rawValue:))
            ?? SettingsDefaults.vehicleType
        self.cachedZoneHash = defaults.string(forKey: SettingsKey.cachedZoneHash)
            ?? SettingsDefaults.cachedZoneHash
        self.cachedMapHash = defaults.string(forKey: SettingsKey.cachedMapHash)
            ?? SettingsDefaults.cachedMapHash
        self.mapHeadingUp = (defaults.object(forKey: SettingsKey.mapHeadingUp) as? Bool)
            ?? SettingsDefaults.mapHeadingUp
        self.mapThemeMode = (defaults.string(forKey: SettingsKey.mapThemeMode))
            .flatMap(MapThemeMode.init(rawValue:)) ?? SettingsDefaults.mapThemeMode
    }
}
