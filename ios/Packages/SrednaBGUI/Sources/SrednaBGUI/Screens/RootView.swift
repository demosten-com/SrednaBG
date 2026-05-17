// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
import SrednaBGCore
import SrednaBGData
import SrednaBGTracking

/// Top-level tab view. The app shell wires this up after constructing the
/// `ZoneTrackingService` + `SettingsStore` + sync callback. Pure SwiftUI;
/// no platform-specific dependencies.
public struct RootView: View {

    public let tracking: ZoneTrackingService
    public let settings: SettingsStore
    public let onSyncTap: () async -> SyncResult
    public let mapStyleURLProvider: (MapTheme) async -> URL?

    /// Outlives the Map tab so its camera + follow state survive a tab
    /// round-trip. SwiftUI's `TabView` tears down off-screen tabs, so
    /// `ZoneMapScreen`'s own `@State` would otherwise reset on every visit.
    @State private var mapSession = MapSessionStore()

    public init(
        tracking: ZoneTrackingService,
        settings: SettingsStore,
        onSyncTap: @escaping () async -> SyncResult,
        mapStyleURLProvider: @escaping (MapTheme) async -> URL?
    ) {
        self.tracking = tracking
        self.settings = settings
        self.onSyncTap = onSyncTap
        self.mapStyleURLProvider = mapStyleURLProvider
    }

    public var body: some View {
        // Sync L10n's sub-bundle selector before the subtree reads it. Computed
        // during body evaluation so every re-render (including the .id() forced
        // rebuild below) picks up the current language.
        _ = { L10n.currentLanguage = settings.appLanguage }()

        return TabView {
            NavigationStack {
                HomeScreen(tracking: tracking, settings: settings)
                    .navigationTitle(L10n.navHome)
                    #if os(iOS)
                    .toolbar(.hidden, for: .navigationBar)
                    #endif
            }
            .tabItem {
                Label {
                    Text(L10n.navHome)
                } icon: {
                    Image("HomeTabIcon", bundle: .module)
                }
            }
            .accessibilityIdentifier("tab-home")

            NavigationStack {
                ZoneMapScreen(
                    tracking: tracking,
                    settings: settings,
                    mapSession: mapSession,
                    mapStyleURLProvider: mapStyleURLProvider,
                    onSyncTap: onSyncTap
                )
            }
            .tabItem { Label(L10n.navMap, systemImage: "map") }
            .accessibilityIdentifier("tab-map")

            NavigationStack {
                SettingsScreen(settings: settings, onSyncTap: onSyncTap)
            }
            .tabItem { Label(L10n.navSettings, systemImage: "gearshape") }
            .accessibilityIdentifier("tab-settings")
        }
        // SwiftUI's Toggle uses a hardcoded system-green for its "on" state and
        // ignores the AccentColor asset. Forcing .tint here cascades to every
        // Toggle (and other tinted controls) under the tab view so they pick
        // up the brand green.
        .tint(.accentColor)
        // Keep the screen awake while tracking is active, regardless of which
        // tab the user is on. iOS resets `isIdleTimerDisabled` on background;
        // the modifier re-asserts the current value on return to foreground.
        .keepScreenAwake(while: tracking.isTracking)
        // View-scoped locale override for SwiftUI's own formatters. Does NOT
        // mutate Bundle.main or Locale.current, so AudioAlertManager's TTS
        // voice selection stays on its own path.
        .environment(\.locale, L10n.locale(for: settings.appLanguage) ?? .current)
        // Force a full subtree rebuild on language change. Needed because
        // `Text(L10n.xxx)` resolves its string at body-evaluation time, and
        // child views that don't read `appLanguage` wouldn't otherwise
        // re-evaluate their bodies when the setting flips.
        .id(settings.appLanguage)
    }
}
