// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SrednaBGCore

/// `UserDefaults` keys for the user-tunable settings. Keep names byte-
/// identical to the Android `SettingsRepository` keys so screenshots, bug
/// reports, and the QA harness's `DebugControlReceiver` setting names line up
/// across platforms.
public enum SettingsKey {
    public static let voiceEnabled = "voice_enabled"
    public static let periodicVoiceUpdates = "periodic_voice_updates"
    public static let announceOnlyWhenOver = "announce_only_when_over"
    public static let appLanguage = "app_language"
    public static let vehicleType = "vehicle_type"
    public static let cachedZoneHash = "cached_zone_hash"
    /// ISO-8601 `version` timestamp of the currently-active zone data, written
    /// alongside `cachedZoneHash`. Mirrors Android `KEY_ZONE_VERSION`.
    public static let cachedZoneVersion = "cached_zone_version"
    public static let cachedMapHash = "cached_map_hash"
    public static let mapHeadingUp = "map_heading_up"
    public static let mapThemeMode = "map_theme_mode"
    public static let mapZoomOverride = "map_zoom_override"
    /// Screenshot harness only: when set, in-zone UI shows this value for
    /// "Max now" instead of the live SpeedStatus computation. Mirrors the
    /// Android `KEY_DEBUG_MAX_SPEED_OVERRIDE`. Writes are gated to the
    /// `#if DEBUG` DebugActionRouter — release builds can read the field
    /// (it stays `nil`) but nothing in the app can mutate it.
    public static let debugMaxSpeedOverride = "debug_max_speed_override"
    /// Hours of inactivity (no zone state transition) after which tracking
    /// auto-stops to spare the battery if the user forgets the app open. `0`
    /// disables the auto-stop. Mirrors Android `KEY_AUTO_STOP_HOURS`.
    public static let autoStopHours = "auto_stop_hours"
    /// QA harness only: when > 0, the inactivity timer compares against this
    /// value in seconds instead of `auto_stop_hours * 3600`. Lets the scenario
    /// fire in ~10 s instead of 3 h. Mirrors the `debug_max_speed_override`
    /// gating — release builds can read the field but the `DebugActionRouter`
    /// setter is `#if DEBUG`-only.
    public static let debugAutoStopSeconds = "debug_auto_stop_seconds"
    /// User opt-out (default on) for the periodic background zone sync. When
    /// off, zones update only via the manual "Sync zones now" action. Mirrors
    /// Android `KEY_ZONE_SYNC_ENABLED`.
    public static let zoneSyncEnabled = "zone_sync_enabled"
}

public enum SettingsDefaults {
    public static let voiceEnabled = true
    public static let periodicVoiceUpdates = true
    public static let announceOnlyWhenOver = true
    public static let appLanguage: AppLanguage = .system
    public static let vehicleType: VehicleType = .car
    public static let cachedZoneHash = ""
    public static let cachedZoneVersion = ""
    public static let cachedMapHash = ""
    public static let mapHeadingUp = false
    public static let mapThemeMode: MapThemeMode = .auto
    public static let mapZoomOverride: Double? = nil
    public static let autoStopHours = 3
    public static let zoneSyncEnabled = true
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
