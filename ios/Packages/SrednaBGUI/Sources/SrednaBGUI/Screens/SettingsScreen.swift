// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
import SrednaBGCore
import SrednaBGData

/// Mirrors `SettingsScreen.kt`: alert threshold slider, voice toggles,
/// language + vehicle pickers, sync button. Bound to `SettingsStore`
/// (`@Observable @MainActor`) so flips persist to UserDefaults immediately.
public struct SettingsScreen: View {

    @Bindable public var settings: SettingsStore
    public let onSyncTap: () async -> SyncResult
    @State private var snackbar: SnackbarMessage?
    @State private var isSyncing = false

    public init(settings: SettingsStore, onSyncTap: @escaping () async -> SyncResult) {
        self.settings = settings
        self.onSyncTap = onSyncTap
    }

    public var body: some View {
        Form {
            alertThresholdSection
            voiceSection
            languageSection
            vehicleSection
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

    private var alertThresholdSection: some View {
        Section(L10n.settingAlertThreshold) {
            Text(String(format: L10n.settingAlertThresholdDesc, settings.alertThresholdKmh))
                .font(.footnote)
                .foregroundStyle(.secondary)
            Slider(
                value: Binding(
                    get: { Double(settings.alertThresholdKmh) },
                    set: { settings.alertThresholdKmh = Int($0.rounded()) }
                ),
                in: 0...20,
                step: 1
            )
        }
    }

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
        Section(L10n.settingLanguage) {
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
        Section(L10n.settingVehicleType) {
            Picker(L10n.settingVehicleType, selection: $settings.vehicleType) {
                Text(L10n.vehicleCar).tag(VehicleType.car)
                Text(L10n.vehicleTruck).tag(VehicleType.truck)
                Text(L10n.vehicleBus).tag(VehicleType.bus)
            }
            .accessibilityIdentifier("settings-vehicle-type")
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
        Section {
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
        }
    }

    private var aboutSection: some View {
        Section {
            Text(String(format: L10n.aboutVersion, "0.1.0"))
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
