// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftData
import SwiftUI
import SrednaBGCore
import SrednaBGData
import SrednaBGTracking

/// Top-level tab view. The app shell wires this up after constructing the
/// `ZoneTrackingService` + `SettingsStore` + sync callback. Pure SwiftUI;
/// no platform-specific dependencies.
///
/// Owns the persistent UI state (`mapSession`, `selectedTab`) and hosts the
/// localized `RootTabs` subtree keyed by `settings.appLanguage`. The `.id`
/// recreates `RootTabs` on every language change while this view's `@State`
/// survives the rebuild, so the Map camera + selected tab don't reset.
public struct RootView: View {

    public let tracking: ZoneTrackingService
    public let settings: SettingsStore
    public let historyStore: HistoryStore
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
        historyStore: HistoryStore,
        onSyncTap: @escaping () async -> SyncResult,
        onZoneSyncToggle: @escaping (Bool) -> Void = { _ in },
        mapStyleURLProvider: @escaping (MapTheme) async -> URL?
    ) {
        self.tracking = tracking
        self.settings = settings
        self.historyStore = historyStore
        self.onSyncTap = onSyncTap
        self.onZoneSyncToggle = onZoneSyncToggle
        self.mapStyleURLProvider = mapStyleURLProvider
    }

    public var body: some View {
        // `RootTabs.init` syncs `L10n.currentLanguage` synchronously before its
        // body (and descendants) resolve any `Text(L10n.xxx)`. The `.id` forces
        // a full subtree rebuild on language change, which re-runs that init —
        // keeping the L10n side effect out of a `body` and correctly ordered.
        RootTabs(
            tracking: tracking,
            settings: settings,
            historyStore: historyStore,
            onSyncTap: onSyncTap,
            onZoneSyncToggle: onZoneSyncToggle,
            mapStyleURLProvider: mapStyleURLProvider,
            mapSession: mapSession,
            selectedTab: $selectedTab
        )
        .id(settings.appLanguage)
    }
}

/// The localized tab subtree. Recreated by `RootView`'s `.id(appLanguage)` on
/// every language change; its `init` is the synchronous hook that points
/// `L10n` at the right sub-bundle before the subtree renders.
private struct RootTabs: View {

    let tracking: ZoneTrackingService
    let settings: SettingsStore
    let historyStore: HistoryStore
    let onSyncTap: () async -> SyncResult
    let onZoneSyncToggle: (Bool) -> Void
    let mapStyleURLProvider: (MapTheme) async -> URL?
    let mapSession: MapSessionStore
    @Binding var selectedTab: String

    init(
        tracking: ZoneTrackingService,
        settings: SettingsStore,
        historyStore: HistoryStore,
        onSyncTap: @escaping () async -> SyncResult,
        onZoneSyncToggle: @escaping (Bool) -> Void,
        mapStyleURLProvider: @escaping (MapTheme) async -> URL?,
        mapSession: MapSessionStore,
        selectedTab: Binding<String>
    ) {
        self.tracking = tracking
        self.settings = settings
        self.historyStore = historyStore
        self.onSyncTap = onSyncTap
        self.onZoneSyncToggle = onZoneSyncToggle
        self.mapStyleURLProvider = mapStyleURLProvider
        self.mapSession = mapSession
        self._selectedTab = selectedTab
        // Sync L10n's sub-bundle selector before the subtree reads it. Done in
        // init (not body) so it's an ordered pre-render step, not a side effect
        // during view evaluation; `RootView`'s `.id(appLanguage)` re-runs this
        // init whenever the language flips.
        L10n.currentLanguage = settings.appLanguage
    }

    var body: some View {
        TabView(selection: $selectedTab) {
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
                HistoryScreen(
                    settings: settings,
                    tracking: tracking,
                    mapSession: mapSession,
                    onShowOnMap: { selectedTab = DebugTabName.map }
                )
            }
            // Attach the History store's SwiftData container so `@Query` in
            // HistoryScreen reads the same context the recorder writes to.
            .modelContainer(historyStore.container)
            .tabItem { Label(L10n.navHistory, systemImage: "clock.arrow.circlepath") }
            .tag(DebugTabName.history)
            .accessibilityIdentifier("tab-history")

            NavigationStack {
                SettingsScreen(
                    settings: settings,
                    onSyncTap: onSyncTap,
                    onZoneSyncToggle: onZoneSyncToggle,
                    zoneCount: tracking.zones.count
                )
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
        // Tracking owns the map from the moment it starts — drop any History
        // "Show on map" highlight so the two never drive the map at once.
        // Watching `isTracking` here covers every start path (Home button and
        // the QA debug listener both flip it via ZoneTrackingService.start());
        // the Tracking package can't reference this UI-layer store itself.
        .onChange(of: tracking.isTracking) { _, isOn in
            if isOn { mapSession.clearHighlight() }
        }
        // View-scoped locale override for SwiftUI's own formatters. Does NOT
        // mutate Bundle.main or Locale.current, so AudioAlertManager's TTS
        // voice selection stays on its own path.
        .environment(\.locale, L10n.locale(for: settings.appLanguage) ?? .current)
    }
}
