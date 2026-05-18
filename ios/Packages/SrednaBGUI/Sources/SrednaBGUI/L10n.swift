// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import Foundation
import SrednaBGData

/// Type-safe accessors for the strings in `Resources/{bg,en}.lproj/Localizable.strings`.
///
/// Strings are resolved through a sub-bundle (`bg.lproj` or `en.lproj`) selected
/// by `currentLanguage`. `RootView` syncs this from `SettingsStore.appLanguage`
/// and stamps an `.id(appLanguage)` on the tab content so the whole subtree
/// rebuilds (and every `Text(L10n.*)` re-evaluates) when the user picks a new
/// language. Reading the fully-resolved `String` at call time — instead of
/// leaning on SwiftUI's `\.locale` env, which only affects strings localized
/// at Text-render time — is what makes this work without changing all 62 call
/// sites.
@MainActor
public enum L10n {

    /// Selects which `.lproj` sub-bundle `loc(_:)` reads from. `.system` falls
    /// through to `Bundle.module`'s own resolution (device language).
    public static var currentLanguage: AppLanguage = .system

    // MARK: Navigation
    public static var navHome: String { loc("navHome") }
    public static var navMap: String { loc("navMap") }
    public static var navSettings: String { loc("navSettings") }

    // MARK: HomeScreen
    public static var statusNotTracking: String { loc("statusNotTracking") }
    public static var tapToStartHint: String { loc("tapToStartHint") }
    public static var statusTrackingOutside: String { loc("statusTrackingOutside") }
    public static var statusInZone: String { loc("statusInZone") }                       // "%@"
    public static var statusExiting: String { loc("statusExiting") }                     // "%@"
    public static var statusOverLimit: String { loc("statusOverLimit") }
    public static var statusWithinLimit: String { loc("statusWithinLimit") }
    public static var statusNowSpeed: String { loc("statusNowSpeed") }                   // "%@"
    public static var avgSpeedLabel: String { loc("avgSpeedLabel") }
    public static var currentSpeedLabel: String { loc("currentSpeedLabel") }
    public static var speedLimit: String { loc("speedLimit") }
    public static var maxForRemainder: String { loc("maxForRemainder") }
    public static var remaining: String { loc("remaining") }
    public static var finalAvgSpeed: String { loc("finalAvgSpeed") }                     // "%@"
    public static var zonesLoaded: String { loc("zonesLoaded") }                         // "%d"
    public static var startTracking: String { loc("startTracking") }
    public static var stopTracking: String { loc("stopTracking") }

    // MARK: Permission gating
    public static var permissionAlwaysRequiredTitle: String { loc("permissionAlwaysRequiredTitle") }
    public static var permissionAlwaysRequiredBody: String { loc("permissionAlwaysRequiredBody") }
    public static var permissionDeniedTitle: String { loc("permissionDeniedTitle") }
    public static var permissionDeniedBody: String { loc("permissionDeniedBody") }
    public static var permissionOpenSettings: String { loc("permissionOpenSettings") }
    public static var permissionTryAgain: String { loc("permissionTryAgain") }

    // MARK: SettingsScreen
    public static var settingAlertThreshold: String { loc("settingAlertThreshold") }
    public static var settingAlertThresholdDesc: String { loc("settingAlertThresholdDesc") } // "%d"
    public static var settingVoiceAlerts: String { loc("settingVoiceAlerts") }
    public static var settingVoiceAlertsDesc: String { loc("settingVoiceAlertsDesc") }
    public static var settingPeriodicUpdates: String { loc("settingPeriodicUpdates") }
    public static var settingPeriodicUpdatesDesc: String { loc("settingPeriodicUpdatesDesc") }
    public static var settingOverspeedOnly: String { loc("settingOverspeedOnly") }
    public static var settingOverspeedOnlyDesc: String { loc("settingOverspeedOnlyDesc") }
    public static var settingLanguage: String { loc("settingLanguage") }
    public static var settingLanguageDesc: String { loc("settingLanguageDesc") }
    public static var languageSystem: String { loc("languageSystem") }
    public static var languageBg: String { loc("languageBg") }
    public static var languageEn: String { loc("languageEn") }
    public static var settingVehicleType: String { loc("settingVehicleType") }
    public static var vehicleCar: String { loc("vehicleCar") }
    public static var vehicleTruck: String { loc("vehicleTruck") }
    public static var vehicleBus: String { loc("vehicleBus") }
    public static var settingAutoStop: String { loc("settingAutoStop") }
    public static var settingAutoStopDesc: String { loc("settingAutoStopDesc") }
    public static var autoStop3h: String { loc("autoStop3h") }
    public static var autoStop6h: String { loc("autoStop6h") }
    public static var autoStopNever: String { loc("autoStopNever") }
    public static var settingMapHeadingUp: String { loc("settingMapHeadingUp") }
    public static var settingMapHeadingUpDesc: String { loc("settingMapHeadingUpDesc") }
    public static var settingMapTheme: String { loc("settingMapTheme") }
    public static var settingMapThemeDesc: String { loc("settingMapThemeDesc") }
    public static var mapThemeAuto: String { loc("mapThemeAuto") }
    public static var mapThemeLight: String { loc("mapThemeLight") }
    public static var mapThemeDark: String { loc("mapThemeDark") }
    public static var settingSyncNow: String { loc("settingSyncNow") }
    public static var syncUpdated: String { loc("syncUpdated") }
    public static var syncUpToDate: String { loc("syncUpToDate") }
    public static var syncFailed: String { loc("syncFailed") }

    // MARK: AboutScreen
    public static var aboutTitle: String { loc("aboutTitle") }
    public static var aboutVersion: String { loc("aboutVersion") }                       // "%@"
    public static var aboutLicense: String { loc("aboutLicense") }
    public static var aboutAttribution: String { loc("aboutAttribution") }
    public static var aboutZoneData: String { loc("aboutZoneData") }

    // MARK: Map
    public static var mapZoomIn: String { loc("mapZoomIn") }
    public static var mapZoomOut: String { loc("mapZoomOut") }
    public static var mapHeadingUp: String { loc("mapHeadingUp") }
    public static var mapNorthUp: String { loc("mapNorthUp") }
    public static var mapFollow: String { loc("mapFollow") }
    public static var mapNoZones: String { loc("mapNoZones") }
    public static var mapLoading: String { loc("mapLoading") }
    public static var mapLoadFailed: String { loc("mapLoadFailed") }
    public static var mapLoadFailedHint: String { loc("mapLoadFailedHint") }
    public static var mapRetry: String { loc("mapRetry") }

    // MARK: AppLanguage → Locale

    /// Maps the user's `AppLanguage` setting to the SwiftUI locale override
    /// applied on `RootView`. `.system` returns `nil` so callers can fall
    /// through to `Locale.current`. Shared between `RootView` and tests.
    public nonisolated static func locale(for language: AppLanguage) -> Locale? {
        switch language {
        case .system: return nil
        case .bg:     return Locale(identifier: "bg")
        case .en:     return Locale(identifier: "en")
        }
    }

    @inline(__always)
    private static func loc(_ key: String) -> String {
        activeBundle.localizedString(forKey: key, value: nil, table: nil)
    }

    private static var activeBundle: Bundle {
        switch currentLanguage {
        case .system: return .module
        case .bg:     return subBundle("bg")
        case .en:     return subBundle("en")
        }
    }

    private static func subBundle(_ localization: String) -> Bundle {
        guard let path = Bundle.module.path(forResource: localization, ofType: "lproj"),
              let sub = Bundle(path: path)
        else { return .module }
        return sub
    }
}

// Not localized on iOS (Android-only keys from android/app/src/main/res/values/strings.xml):
// app_name, nav_history, no_zones_loaded, map_user_position, map_recenter,
// map_follow_user_on, map_follow_user_off, map_orientation_north_up,
// map_orientation_heading_up, zone_complete, max_for_remainder_format, retry_sync,
// trip_history_coming_soon, notification_channel_tracking,
// notification_channel_tracking_description, notification_tracking_title,
// notification_tracking_text, accessibility_in_zone, accessibility_exiting,
// auto_routing_cue, auto_final_speed, auto_zone_end, auto_settings,
// auto_monitoring_hint. Port on demand when iOS gains the corresponding feature.
