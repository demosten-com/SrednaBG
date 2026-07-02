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
/// Settings keys mirror `SettingsRepository.kt` byte-identically so the QA
/// harness can drive both platforms with the same key names.
@Observable
@MainActor
public final class SettingsStore {

    @ObservationIgnored
    private let defaults: UserDefaults

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

    public var cachedZoneVersion: String {
        didSet { defaults.set(cachedZoneVersion, forKey: SettingsKey.cachedZoneVersion) }
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

    public var mapZoomOverride: Double? {
        didSet {
            if let value = mapZoomOverride, value != 0 {
                defaults.set(value, forKey: SettingsKey.mapZoomOverride)
            } else {
                defaults.removeObject(forKey: SettingsKey.mapZoomOverride)
            }
        }
    }

    public var debugMaxSpeedOverride: Int? {
        didSet {
            if let value = debugMaxSpeedOverride {
                defaults.set(value, forKey: SettingsKey.debugMaxSpeedOverride)
            } else {
                defaults.removeObject(forKey: SettingsKey.debugMaxSpeedOverride)
            }
        }
    }

    public var autoStopHours: Int {
        didSet { defaults.set(autoStopHours, forKey: SettingsKey.autoStopHours) }
    }

    public var zoneSyncEnabled: Bool {
        didSet { defaults.set(zoneSyncEnabled, forKey: SettingsKey.zoneSyncEnabled) }
    }

    /// How long completed zone traversals are kept in History, as the raw
    /// string token (`none | 1month | 3months | 6months`). Map to
    /// `HistoryRetention` via `HistoryRetention.fromSetting(_:)` for gating /
    /// pruning. Stored as a string (not an Int) to match Android.
    public var historyRetention: String {
        didSet { defaults.set(historyRetention, forKey: SettingsKey.historyRetention) }
    }

    public var debugAutoStopSeconds: Int? {
        didSet {
            if let value = debugAutoStopSeconds, value > 0 {
                defaults.set(value, forKey: SettingsKey.debugAutoStopSeconds)
            } else {
                defaults.removeObject(forKey: SettingsKey.debugAutoStopSeconds)
            }
        }
    }

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults

        // Initial reads bypass `didSet` (Swift does not invoke property observers
        // during `init`), so this hydration does not loop back into UserDefaults.
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
        self.cachedZoneVersion = defaults.string(forKey: SettingsKey.cachedZoneVersion)
            ?? SettingsDefaults.cachedZoneVersion
        self.cachedMapHash = defaults.string(forKey: SettingsKey.cachedMapHash)
            ?? SettingsDefaults.cachedMapHash
        self.mapHeadingUp = (defaults.object(forKey: SettingsKey.mapHeadingUp) as? Bool)
            ?? SettingsDefaults.mapHeadingUp
        self.mapThemeMode = (defaults.string(forKey: SettingsKey.mapThemeMode))
            .flatMap(MapThemeMode.init(rawValue:)) ?? SettingsDefaults.mapThemeMode
        let storedZoom = (defaults.object(forKey: SettingsKey.mapZoomOverride) as? Double)
        self.mapZoomOverride = (storedZoom == 0) ? nil : storedZoom
        self.debugMaxSpeedOverride = defaults.object(forKey: SettingsKey.debugMaxSpeedOverride) as? Int
        self.autoStopHours = (defaults.object(forKey: SettingsKey.autoStopHours) as? Int)
            ?? SettingsDefaults.autoStopHours
        self.zoneSyncEnabled = (defaults.object(forKey: SettingsKey.zoneSyncEnabled) as? Bool)
            ?? SettingsDefaults.zoneSyncEnabled
        self.historyRetention = defaults.string(forKey: SettingsKey.historyRetention)
            ?? SettingsDefaults.historyRetention
        self.debugAutoStopSeconds = defaults.object(forKey: SettingsKey.debugAutoStopSeconds) as? Int
    }
}
