// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SrednaBGCore

/// `UserDefaults` keys for the eight user-tunable settings. Keep names byte-
/// identical to the Android `SettingsRepository` keys so screenshots, bug
/// reports, and the QA harness's `DebugControlReceiver` setting names line up
/// across platforms.
public enum SettingsKey {
    public static let alertThresholdKmh = "alert_threshold_kmh"
    public static let voiceEnabled = "voice_enabled"
    public static let periodicVoiceUpdates = "periodic_voice_updates"
    public static let announceOnlyWhenOver = "announce_only_when_over"
    public static let appLanguage = "app_language"
    public static let vehicleType = "vehicle_type"
    public static let cachedZoneHash = "cached_zone_hash"
    public static let cachedMapHash = "cached_map_hash"
    public static let mapHeadingUp = "map_heading_up"
    public static let mapThemeMode = "map_theme_mode"
}

public enum SettingsDefaults {
    public static let alertThresholdKmh = 5
    public static let voiceEnabled = true
    public static let periodicVoiceUpdates = true
    public static let announceOnlyWhenOver = true
    public static let appLanguage: AppLanguage = .system
    public static let vehicleType: VehicleType = .car
    public static let cachedZoneHash = ""
    public static let cachedMapHash = ""
    public static let mapHeadingUp = false
    public static let mapThemeMode: MapThemeMode = .auto
}

public enum AppLanguage: String, Sendable, CaseIterable, Codable {
    case system
    case bg
    case en

    /// Resolve to the language a TTS / Locale call should actually use,
    /// honoring the device language when "system" is selected. Mirrors
    /// `resolveVoiceLanguage` in Android's `SettingsRepository.kt`.
    public func resolvedVoiceLanguage(deviceLanguage: String) -> AppLanguage {
        switch self {
        case .bg, .en:
            return self
        case .system:
            return deviceLanguage == "bg" ? .bg : .en
        }
    }
}
