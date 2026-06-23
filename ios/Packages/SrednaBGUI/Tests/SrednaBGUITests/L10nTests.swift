// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import Foundation
import Testing
import SrednaBGData
@testable import SrednaBGUI

@MainActor
@Suite("L10n")
struct L10nTests {

    /// Every key shipped in `Resources/{bg,en}.lproj/Localizable.strings`.
    /// Keep in sync with `L10n.swift`; `everyL10nKeyHasBgAndEnTranslation`
    /// enforces parity with the on-disk strings files.
    private static let allKeys: [String] = [
        "navHome", "navMap", "navSettings",
        "statusNotTracking", "tapToStartHint", "statusTrackingOutside",
        "statusInZone", "statusExiting", "statusOverLimit", "statusWithinLimit",
        "statusNowSpeed", "avgSpeedLabel", "currentSpeedLabel", "speedLimit",
        "maxForRemainder", "remaining", "finalAvgSpeed", "zonesLoaded",
        "startTracking", "stopTracking",
        "settingVoiceAlerts", "settingVoiceAlertsDesc",
        "settingPeriodicUpdates", "settingPeriodicUpdatesDesc",
        "settingOverspeedOnly", "settingOverspeedOnlyDesc",
        "settingLanguage", "settingLanguageDesc",
        "languageSystem", "languageBg", "languageEn",
        "settingVehicleType", "vehicleCar", "vehicleTruck", "vehicleBus",
        "settingMapHeadingUp", "settingMapHeadingUpDesc",
        "settingSyncNow", "syncUpdated", "syncUpToDate", "syncFailed",
        "settingZones", "settingZoneDataDate", "settingZoneDataHash",
        "aboutTitle", "aboutVersion", "aboutLicense", "aboutAttribution", "aboutZoneData",
        "mapZoomIn", "mapZoomOut", "mapHeadingUp", "mapNorthUp", "mapFollow", "mapNoZones"
    ]

    /// Sanity: every settings-key string used by `SettingsScreen` is non-empty.
    /// Catches future renames that drop a key without updating the screen.
    @Test
    func criticalKeysAreNonEmpty() {
        let keys: [String] = [
            L10n.statusNotTracking,
            L10n.startTracking,
            L10n.stopTracking,
            L10n.settingVoiceAlerts,
            L10n.settingPeriodicUpdates,
            L10n.settingOverspeedOnly,
            L10n.settingLanguage,
            L10n.settingVehicleType,
            L10n.settingMapHeadingUp,
            L10n.settingSyncNow,
            L10n.syncUpdated,
            L10n.syncUpToDate,
            L10n.syncFailed
        ]
        for key in keys {
            #expect(!key.isEmpty)
        }
    }

    @Test
    func formatStringsHaveExpectedPlaceholders() {
        #expect(L10n.statusInZone.contains("%@"))
        #expect(L10n.statusExiting.contains("%@"))
        #expect(L10n.statusNowSpeed.contains("%@"))
        #expect(L10n.finalAvgSpeed.contains("%@"))
        #expect(L10n.zonesLoaded.contains("%d"))
        #expect(L10n.aboutVersion.contains("%@"))
    }

    /// Guards against a future edit that drops `resources: [.process("Resources")]`
    /// from the SrednaBGUI target in `Package.swift` — without it, `Bundle.module`
    /// no longer exposes the `.lproj/Localizable.strings` files and every
    /// `L10n.*` falls back to the raw key.
    @Test
    func bundleModuleResolvesLocalizableStrings() throws {
        let bg = Bundle.module.url(forResource: "Localizable", withExtension: "strings", subdirectory: nil, localization: "bg")
        let en = Bundle.module.url(forResource: "Localizable", withExtension: "strings", subdirectory: nil, localization: "en")
        #expect(bg != nil, "bg.lproj/Localizable.strings not found in Bundle.module")
        #expect(en != nil, "en.lproj/Localizable.strings not found in Bundle.module")
    }

    /// Every key listed in `L10n.swift` must appear in both the BG and EN
    /// strings files with a non-empty value.
    @Test
    func everyL10nKeyHasBgAndEnTranslation() throws {
        let bg = try Self.loadStrings(localization: "bg")
        let en = try Self.loadStrings(localization: "en")
        for key in Self.allKeys {
            #expect(bg[key]?.isEmpty == false, "bg missing: \(key)")
            #expect(en[key]?.isEmpty == false, "en missing: \(key)")
        }
    }

    /// BG and EN must use the same format specifiers. Catches a stray `%s`
    /// (Android style) leaking in or a translator dropping a placeholder.
    @Test
    func formatSpecifiersMatchAcrossLanguages() throws {
        let bg = try Self.loadStrings(localization: "bg")
        let en = try Self.loadStrings(localization: "en")
        for key in Self.allKeys {
            guard let bgValue = bg[key], let enValue = en[key] else { continue }
            #expect(Self.specifiers(in: bgValue) == Self.specifiers(in: enValue),
                    "format specifier mismatch for \(key): bg=\(bgValue) en=\(enValue)")
        }
    }

    /// Proves both `.lproj` bundles contain the expected values by loading
    /// each as a sub-bundle directly. This is a stricter check than
    /// `String(localized:, locale:)` which in a unit-test process tends to
    /// resolve through the host's `preferredLocalizations` fallback chain
    /// instead of honoring the passed locale for `.lproj` selection.
    @Test
    func lprojBundlesContainExpectedValues() throws {
        let bgPath = try #require(Bundle.module.path(forResource: "bg", ofType: "lproj"))
        let enPath = try #require(Bundle.module.path(forResource: "en", ofType: "lproj"))
        let bgBundle = try #require(Bundle(path: bgPath))
        let enBundle = try #require(Bundle(path: enPath))
        #expect(bgBundle.localizedString(forKey: "navHome", value: nil, table: nil) == "Начало")
        #expect(enBundle.localizedString(forKey: "navHome", value: nil, table: nil) == "Home")
        #expect(bgBundle.localizedString(forKey: "statusOverLimit", value: nil, table: nil) == "Превишение")
        #expect(enBundle.localizedString(forKey: "statusOverLimit", value: nil, table: nil) == "Over limit")
    }

    /// Pins the plumbing `RootView` relies on to flip the locale env.
    @Test
    func appLanguageMapsToExpectedLocale() {
        #expect(L10n.locale(for: .bg)?.identifier == "bg")
        #expect(L10n.locale(for: .en)?.identifier == "en")
        #expect(L10n.locale(for: .system) == nil)
    }

    // MARK: - Helpers

    private static func loadStrings(localization: String) throws -> [String: String] {
        let url = try #require(
            Bundle.module.url(forResource: "Localizable", withExtension: "strings",
                              subdirectory: nil, localization: localization)
        )
        let data = try Data(contentsOf: url)
        let plist = try PropertyListSerialization.propertyList(from: data, format: nil)
        return (plist as? [String: String]) ?? [:]
    }

    /// Extracts printf-style specifiers from a format string in order.
    /// A swap like `%@ %d` vs `%d %@` is detected.
    private static func specifiers(in text: String) -> [String] {
        var result: [String] = []
        var i = text.startIndex
        while let pct = text[i...].firstIndex(of: "%") {
            var j = text.index(after: pct)
            while j < text.endIndex, "0123456789$.-+ #".contains(text[j]) {
                j = text.index(after: j)
            }
            if j < text.endIndex {
                let conv = text[j]
                if "@dsfxXoeEgG".contains(conv) {
                    result.append(String(text[pct...j]))
                }
                i = text.index(after: j)
            } else {
                break
            }
        }
        return result
    }
}
