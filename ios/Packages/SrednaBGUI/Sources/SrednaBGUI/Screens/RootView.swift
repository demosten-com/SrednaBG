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
    public let onZoneSyncToggle: (Bool) -> Void
    public let mapStyleURLProvider: (MapTheme) async -> URL?

    /// Outlives the Map tab so its camera + follow state survive a tab
    /// round-trip. SwiftUI's `TabView` tears down off-screen tabs, so
    /// `ZoneMapScreen`'s own `@State` would otherwise reset on every visit.
    @State private var mapSession = MapSessionStore()

    /// Bound to `TabView`'s `selection` so the QA harness can drive tab
    /// switches over HTTP (via `DebugActionRouter`'s `/tab` endpoint, only
    /// observed under `#if DEBUG`). User taps update the binding directly,
    /// matching default `TabView` behavior.
    @State private var selectedTab: String = DebugTabName.home

    public init(
        tracking: ZoneTrackingService,
        settings: SettingsStore,
        onSyncTap: @escaping () async -> SyncResult,
        onZoneSyncToggle: @escaping (Bool) -> Void = { _ in },
        mapStyleURLProvider: @escaping (MapTheme) async -> URL?
    ) {
        self.tracking = tracking
        self.settings = settings
        self.onSyncTap = onSyncTap
        self.onZoneSyncToggle = onZoneSyncToggle
        self.mapStyleURLProvider = mapStyleURLProvider
    }

    public var body: some View {
        // Sync L10n's sub-bundle selector before the subtree reads it. Computed
        // during body evaluation so every re-render (including the .id() forced
        // rebuild below) picks up the current language.
        _ = { L10n.currentLanguage = settings.appLanguage }()

        return TabView(selection: $selectedTab) {
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
            .tag(DebugTabName.home)
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
            .tag(DebugTabName.map)
            .accessibilityIdentifier("tab-map")

            NavigationStack {
                SettingsScreen(settings: settings, onSyncTap: onSyncTap, onZoneSyncToggle: onZoneSyncToggle)
            }
            .tabItem { Label(L10n.navSettings, systemImage: "gearshape") }
            .tag(DebugTabName.settings)
            .accessibilityIdentifier("tab-settings")
        }
        #if DEBUG
        // QA back-channel: DebugActionRouter posts this notification on
        // GET /tab?which=<name>. Only observed in Debug builds — release
        // builds never load DebugControlServer so the notification can't
        // arrive there anyway, but the modifier itself is also gated.
        .onReceive(NotificationCenter.default.publisher(for: DebugTabName.selectionNotification)) { note in
            if let tab = note.userInfo?[DebugTabName.userInfoKey] as? String,
               DebugTabName.isValid(tab) {
                selectedTab = tab
            }
        }
        #endif
        // SwiftUI's Toggle uses a hardcoded system-green for its "on" state and
        // ignores the AccentColor asset. Forcing .tint here cascades to every
        // Toggle (and other tinted controls) under the tab view so they pick
        // up the brand green.
        .tint(.accentColor)
        // Keep the screen awake while tracking is active, regardless of which
        // tab the user is on. iOS resets `isIdleTimerDisabled` on background;
        // the modifier re-asserts the current value on return to foreground.
        .keepScreenAwake(while: tracking.isTracking)
        // Lock Home + Settings to portrait (never designed for landscape) while
        // letting the Map tab rotate freely. `initial: true` asserts portrait at
        // launch (Home is the default tab). Driven off `selectedTab` so user
        // taps and the DEBUG `/tab` back-channel share one path. No-op on macOS.
        .onChange(of: selectedTab, initial: true) { _, tab in
            OrientationLock.shared.apply(tab == DebugTabName.map ? .free : .portrait)
        }
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
