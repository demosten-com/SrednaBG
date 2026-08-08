// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
import SrednaBGCore
import SrednaBGData

/// Mirrors `SettingsScreen.kt`: voice toggles, language + vehicle pickers,
/// sync button. Bound to `SettingsStore`
/// (`@Observable @MainActor`) so flips persist to UserDefaults immediately.
public struct SettingsScreen: View {

    @Bindable public var settings: SettingsStore
    public let onSyncTap: () async -> SyncResult
    public let onZoneSyncToggle: (Bool) -> Void
    /// Size of the catalog the app actually holds — read from the live zone
    /// list by the caller so SwiftUI observation stays on that owner.
    public let zoneCount: Int
    @State private var snackbar: SnackbarMessage?
    @State private var isSyncing = false

    public init(
        settings: SettingsStore,
        onSyncTap: @escaping () async -> SyncResult,
        onZoneSyncToggle: @escaping (Bool) -> Void = { _ in },
        zoneCount: Int = 0
    ) {
        self.settings = settings
        self.onSyncTap = onSyncTap
        self.onZoneSyncToggle = onZoneSyncToggle
        self.zoneCount = zoneCount
    }

    public var body: some View {
        Form {
            voiceSection
            languageSection
            vehicleSection
            autoStopSection
            historySection
            mapSection
            syncSection
            aboutSection
        }
        .navigationTitle(L10n.navSettings)
        .overlay(alignment: .bottom) {
            if let snackbar {
                Text(snackbar.text)
                    .font(.callout)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(.ultraThinMaterial, in: Capsule())
                    .padding(.bottom, 24)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .id(snackbar.id)
            }
        }
        .animation(.snappy, value: snackbar?.id)
    }

    // MARK: sections

    private var voiceSection: some View {
        Section(L10n.settingVoiceAlerts) {
            Toggle(L10n.settingVoiceAlerts, isOn: $settings.voiceEnabled)
                .accessibilityIdentifier("settings-voice-enabled")
            Toggle(L10n.settingPeriodicUpdates, isOn: $settings.periodicVoiceUpdates)
                .disabled(!settings.voiceEnabled)
                .accessibilityIdentifier("settings-periodic-voice-updates")
            Toggle(L10n.settingOverspeedOnly, isOn: $settings.announceOnlyWhenOver)
                .disabled(!settings.voiceEnabled || !settings.periodicVoiceUpdates)
                .padding(.leading, 16)
                .accessibilityIdentifier("settings-announce-only-when-over")
        }
    }

    private var languageSection: some View {
        Section {
            Picker(L10n.settingLanguage, selection: $settings.appLanguage) {
                Text(L10n.languageSystem).tag(AppLanguage.system)
                Text(L10n.languageBg).tag(AppLanguage.bg)
                Text(L10n.languageEn).tag(AppLanguage.en)
            }
            .accessibilityIdentifier("settings-app-language")
            Text(L10n.settingLanguageDesc)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }

    private var vehicleSection: some View {
        Section {
            Picker(L10n.settingVehicleType, selection: $settings.vehicleType) {
                Text(L10n.vehicleCar).tag(VehicleType.car)
                Text(L10n.vehicleTruck).tag(VehicleType.truck)
                Text(L10n.vehicleBus).tag(VehicleType.bus)
            }
            .accessibilityIdentifier("settings-vehicle-type")
        }
    }

    private var autoStopSection: some View {
        Section {
            Picker(L10n.settingAutoStop, selection: $settings.autoStopHours) {
                Text(L10n.autoStop3h).tag(3)
                Text(L10n.autoStop6h).tag(6)
                Text(L10n.autoStopNever).tag(0)
            }
            .accessibilityIdentifier("settings-auto-stop-hours")
            Text(L10n.settingAutoStopDesc)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }

    private var historySection: some View {
        Section {
            Picker(L10n.settingHistoryRetention, selection: $settings.historyRetention) {
                Text(L10n.historyRetentionNone).tag("none")
                Text(L10n.historyRetention1Month).tag("1month")
                Text(L10n.historyRetention3Months).tag("3months")
                Text(L10n.historyRetention6Months).tag("6months")
            }
            .accessibilityIdentifier("settings-history-retention")
            Text(L10n.settingHistoryRetentionDesc)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }

    private var mapSection: some View {
        Section(L10n.navMap) {
            Toggle(L10n.settingMapHeadingUp, isOn: $settings.mapHeadingUp)
                .accessibilityIdentifier("settings-map-heading-up")
            Text(L10n.settingMapHeadingUpDesc)
                .font(.footnote)
                .foregroundStyle(.secondary)
            Picker(L10n.settingMapTheme, selection: $settings.mapThemeMode) {
                Text(L10n.mapThemeAuto).tag(MapThemeMode.auto)
                Text(L10n.mapThemeLight).tag(MapThemeMode.light)
                Text(L10n.mapThemeDark).tag(MapThemeMode.dark)
            }
            .accessibilityIdentifier("settings-map-theme")
            Text(L10n.settingMapThemeDesc)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }

    private var syncSection: some View {
        Section(L10n.settingZones) {
            // Automatic zone updates — opt-out for the periodic background
            // sync. The "Sync zones now" button below stays available
            // regardless (it calls onSyncTap directly, not gated by this).
            Toggle(L10n.settingZoneSync, isOn: $settings.zoneSyncEnabled)
                .onChange(of: settings.zoneSyncEnabled) { _, newValue in
                    onZoneSyncToggle(newValue)
                }
                .accessibilityIdentifier("settings-zone-sync")
            Text(L10n.settingZoneSyncDesc)
                .font(.footnote)
                .foregroundStyle(.secondary)
            Button {
                Task { await runSync() }
            } label: {
                HStack {
                    if isSyncing { ProgressView() }
                    Text(L10n.settingSyncNow)
                }
            }
            .disabled(isSyncing)
            .accessibilityIdentifier("settings-sync-now")
            Text(String(
                format: L10n.settingZoneDataDate,
                ZoneDataFormat.formatVersion(
                    settings.cachedZoneVersion,
                    locale: L10n.locale(for: settings.appLanguage) ?? .current
                )
            ))
            .font(.footnote)
            .foregroundStyle(.secondary)
            .accessibilityIdentifier("settings-zone-data-date")
            Text(String(format: L10n.settingZoneDataCount, zoneCount))
                .font(.footnote)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("settings-zone-data-count")
            Text(String(format: L10n.settingZoneDataHash, ZoneDataFormat.shortHash(settings.cachedZoneHash)))
                .font(.footnote)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("settings-zone-data-hash")
        }
    }

    private var aboutSection: some View {
        Section {
            Text(String(format: L10n.aboutVersion, Bundle.appShortVersion))
                .font(.footnote)
                .foregroundStyle(.secondary)
            Text(L10n.aboutLicense)
                .font(.footnote)
                .foregroundStyle(.secondary)
            Text(L10n.aboutAttribution)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(L10n.aboutZoneData)
                .font(.caption)
                .foregroundStyle(.secondary)
        } header: {
            VStack(alignment: .leading, spacing: 8) {
                Text(L10n.aboutTitle)
                Image("SrednaBGLogoHorizontal", bundle: .module)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity, maxHeight: 80)
                    .foregroundStyle(Color.accentColor)
                    .accessibilityLabel("SrednaBG")
                    .padding(.bottom, 4)
            }
        }
    }

    private func runSync() async {
        isSyncing = true
        defer { isSyncing = false }
        let result = await onSyncTap()
        let text: String
        switch result {
        case .updated:  text = L10n.syncUpdated
        case .upToDate: text = L10n.syncUpToDate
        case .failed:   text = L10n.syncFailed
        }
        snackbar = SnackbarMessage(text: text)
    }
}

private struct SnackbarMessage: Identifiable, Equatable {
    let id = UUID()
    let text: String
}
