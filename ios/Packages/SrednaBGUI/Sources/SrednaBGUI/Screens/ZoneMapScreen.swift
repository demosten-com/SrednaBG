// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
import SrednaBGCore
import SrednaBGData
import SrednaBGMapCore
import SrednaBGTracking

/// Map tab. Mounts `MapLibreView` as soon as a style URL resolves and keeps
/// it mounted across transient load failures. A loading overlay covers the
/// map until MapLibre emits its first fully-rendered frame; a retry banner
/// overlays on style-load failure. Only when no style URL can be produced
/// at all do we fall back to the sync-CTA empty state.
public struct ZoneMapScreen: View {

    @Bindable public var tracking: ZoneTrackingService
    @Bindable public var settings: SettingsStore
    @Bindable public var mapSession: MapSessionStore
    public let mapStyleURLProvider: (MapTheme) async -> URL?
    public let onSyncTap: () async -> SyncResult

    @State private var styleURL: URL?
    @State private var resolvedTheme: MapTheme?
    @State private var lastEvaluatedTheme: MapTheme = .light
    #if os(iOS)
    @State private var pendingCommand: MapLibreView.MapCommand?
    #endif
    @State private var isSyncing: Bool = false
    @State private var isResolvingStyle: Bool = false
    @State private var styleLoadFailed: Bool = false
    @State private var isMapReady: Bool = false
    @State private var isRetryingStyle: Bool = false
    @State private var nowTick: Date = Date()

    /// Wakes the auto-theme resolver every minute so the map flips into dark
    /// (or back to light) within ~60s of crossing civil twilight at the
    /// user's location. Cheap — the resolver is sub-millisecond.
    ///
    /// `@State` so SwiftUI owns the autoconnected publisher's lifecycle: a
    /// plain `let` is rebuilt every time this View struct is re-evaluated,
    /// spinning up (and tearing down) a fresh timer on each render.
    @State private var themeTimer = Timer.publish(every: 60, on: .main, in: .common).autoconnect()

    public init(
        tracking: ZoneTrackingService,
        settings: SettingsStore,
        mapSession: MapSessionStore,
        mapStyleURLProvider: @escaping (MapTheme) async -> URL?,
        onSyncTap: @escaping () async -> SyncResult
    ) {
        self.tracking = tracking
        self.settings = settings
        self.mapSession = mapSession
        self.mapStyleURLProvider = mapStyleURLProvider
        self.onSyncTap = onSyncTap
    }

    public var body: some View {
        ZStack {
            mapSurface
            if showLoadingOverlay {
                loadingOverlay
                    .transition(.opacity)
            }
            VStack {
                if styleLoadFailed, styleURL != nil {
                    failureBanner
                        .padding(.horizontal, 12)
                        .padding(.top, 12)
                } else if case .inZone(let inZone) = tracking.zoneState {
                    StatusChip(
                        inZone: inZone,
                        currentSpeedKmh: tracking.currentPosition?.speed,
                        limitKmh: settings.vehicleType.limit(inZone.zone.speedLimits)
                    )
                        .padding(.horizontal, 12)
                        .padding(.top, 12)
                } else if case .unmeasured(let unmeasured) = tracking.zoneState {
                    UnmeasuredChip(
                        unmeasured: unmeasured,
                        currentSpeedKmh: tracking.currentPosition?.speed,
                        limitKmh: settings.vehicleType.limit(unmeasured.zone.speedLimits)
                    )
                        .padding(.horizontal, 12)
                        .padding(.top, 12)
                }
                Spacer()
                if styleURL != nil {
                    controls
                }
            }
            // Match the overlay chrome to the active map theme so
            // `.ultraThinMaterial`, status chips, and button text stay readable
            // on whichever style is rendered — without this lock SwiftUI follows
            // the system appearance and the chrome can clash with the map (e.g.
            // dark chrome over light tiles or vice versa).
            //
            // Scoped to the chrome overlay ONLY — applying it to the screen's
            // content root made SwiftUI push the override onto the tab's hosting
            // controller, which the shared `UITabBar` then inherited and kept
            // (dark tab bar lingering on Home/Settings after a night-mode map).
            .environment(\.colorScheme, lastEvaluatedTheme == .dark ? .dark : .light)
        }
        .animation(.easeInOut(duration: 0.2), value: showLoadingOverlay)
        #if os(iOS)
        // Hide the nav bar entirely on iOS so the map can bleed into the
        // top safe area — the tab bar's "Map" label already tells the user
        // where they are. `macOS` (preview / tests) keeps its default title.
        .toolbar(.hidden, for: .navigationBar)
        #endif
        .task { await resolveStyleURLIfNeeded() }
        .onAppear {
            reevaluateThemeIfNeeded()
            #if os(iOS)
            applyZoomOverrideIfNeeded()
            fitHighlightIfNeeded()
            #endif
        }
        .onChange(of: settings.mapThemeMode) { _, _ in reevaluateThemeIfNeeded() }
        .onChange(of: tracking.currentPosition?.lat) { _, _ in reevaluateThemeIfNeeded() }
        #if os(iOS)
        .onChange(of: settings.mapZoomOverride) { _, _ in applyZoomOverrideIfNeeded() }
        .onChange(of: mapSession.highlight) { _, _ in fitHighlightIfNeeded() }
        #endif
        .onReceive(themeTimer) { now in
            nowTick = now
            reevaluateThemeIfNeeded()
        }
    }

    #if os(iOS)
    @MainActor
    private func applyZoomOverrideIfNeeded() {
        guard let override = settings.mapZoomOverride else { return }
        pendingCommand = .zoomTo(override)
    }
    #endif

    @ViewBuilder
    private var mapSurface: some View {
        #if os(iOS)
        if let url = styleURL {
            MapLibreView(
                styleURL: url,
                zones: tracking.zones,
                activeZoneId: activeZoneId,
                currentPosition: tracking.currentPosition,
                displayPosition: snapToZone(tracking.currentPosition, state: tracking.zoneState),
                zoneState: tracking.zoneState,
                headingUp: settings.mapHeadingUp,
                mapSession: mapSession,
                zoomOverride: settings.mapZoomOverride,
                highlightColor: highlightColor,
                highlightUser: highlightUser,
                pendingCommand: $pendingCommand,
                styleLoadFailed: $styleLoadFailed,
                isMapReady: $isMapReady
            )
            // UIViewRepresentable's MLNMapView has no intrinsic content size
            // — without this modifier the view collapses to 0×0 and MapLibre
            // never renders a pixel, even though the style loads.
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .ignoresSafeArea()
        } else {
            emptyState
        }
        #else
        emptyState
        #endif
    }

    private var showLoadingOverlay: Bool {
        if styleURL == nil { return false }       // empty state renders its own spinner
        if styleLoadFailed { return false }       // retry banner renders instead
        return !isMapReady                         // mounted but first frame not rendered yet
    }

    private var loadingOverlay: some View {
        ZStack {
            Color(white: 0.96)
            VStack(spacing: 12) {
                ProgressView()
                    .scaleEffect(1.4)
                Text(L10n.mapLoading)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .ignoresSafeArea()
    }

    private var failureBanner: some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(L10n.mapLoadFailed)
                    .font(.subheadline.weight(.semibold))
                Text(L10n.mapLoadFailedHint)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Button {
                Task { await retryStyleLoad() }
            } label: {
                if isRetryingStyle {
                    ProgressView()
                } else {
                    Text(L10n.mapRetry)
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(isRetryingStyle)
        }
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private var emptyState: some View {
        Rectangle()
            .fill(Color(white: 0.92))
            .overlay(
                VStack(spacing: 16) {
                    if isResolvingStyle {
                        ProgressView()
                        Text(L10n.mapLoading)
                            .foregroundStyle(.secondary)
                    } else {
                        Text(L10n.mapNoZones)
                            .multilineTextAlignment(.center)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 24)
                        Button {
                            Task { await runSync() }
                        } label: {
                            if isSyncing {
                                ProgressView()
                            } else {
                                Label(L10n.settingSyncNow, systemImage: "arrow.clockwise")
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isSyncing)
                    }
                }
            )
            .ignoresSafeArea()
    }

    private var controls: some View {
        HStack(spacing: 8) {
            Toggle(isOn: $settings.mapHeadingUp) {
                Label(
                    settings.mapHeadingUp ? L10n.mapHeadingUp : L10n.mapNorthUp,
                    systemImage: settings.mapHeadingUp ? "location.north.line" : "compass.drawing"
                )
                .labelStyle(.iconOnly)
            }
            .toggleStyle(.button)

            Spacer()

            #if os(iOS)
            Button {
                pendingCommand = .zoomOut
            } label: {
                Image(systemName: "minus.magnifyingglass")
                    .accessibilityLabel(L10n.mapZoomOut)
            }
            .buttonStyle(.bordered)

            Button {
                pendingCommand = .zoomIn
            } label: {
                Image(systemName: "plus.magnifyingglass")
                    .accessibilityLabel(L10n.mapZoomIn)
            }
            .buttonStyle(.bordered)

            Toggle(isOn: Binding(
                get: { mapSession.isFollowing },
                set: { newValue in
                    mapSession.isFollowing = newValue
                    // Turning follow back on also snaps the camera to the
                    // user — turning it off just stops tracking and leaves
                    // the camera wherever it was.
                    if newValue { pendingCommand = .recenter }
                }
            )) {
                Label(L10n.mapFollow, systemImage: mapSession.isFollowing ? "scope" : "location.viewfinder")
                    .labelStyle(.iconOnly)
            }
            .toggleStyle(.button)
            #endif
        }
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .padding(12)
    }

    private var activeZoneId: String? {
        switch tracking.zoneState {
        case .inZone(let inZone): return inZone.zone.id
        case .exiting(let exiting): return exiting.zone.id
        // We know exactly which zone we're in even when we can't measure it, so
        // it still gets highlighted — just in the neutral colour.
        case .unmeasured(let unmeasured): return unmeasured.zone.id
        case .outside: return effectiveHighlight?.zone.id
        }
    }

    /// The History "Show on map" request, honored only while tracking is off
    /// and its zone still resolves in the catalog (a sync can delete zones).
    private var effectiveHighlight: (request: MapHighlight, zone: Zone)? {
        guard !tracking.isTracking, let request = mapSession.highlight,
              let zone = tracking.zones.first(where: { $0.id == request.zoneId })
        else { return nil }
        return (request, zone)
    }

    #if os(iOS)
    /// Verdict line color for the highlighted zone — the trip's binary result
    /// (green within limit, red over), never the live traffic light.
    private var highlightColor: UIColor? {
        effectiveHighlight.map {
            statusUIColor($0.request.isOverLimit ? zoneColorRed : zoneColorGreen)
        }
    }

    /// Synthetic user-arrow fix marking the highlighted traversal's start,
    /// pointed straight at the zone's end point — the reading is "you drove
    /// from here to there", not the instantaneous road heading.
    private var highlightUser: GpsPoint? {
        guard let zone = effectiveHighlight?.zone else { return nil }
        return GpsPoint(
            lat: zone.start.lat,
            lng: zone.start.lng,
            speed: 0,
            timestamp: 0,
            bearing: bearingBetween(zone.start.lat, zone.start.lng, zone.end.lat, zone.end.lng)
        )
    }

    /// One-shot camera fit per "Show on map" press, keyed on the requestId so
    /// a tab round-trip keeps the user's pan/zoom while a fresh press re-fits.
    @MainActor
    private func fitHighlightIfNeeded() {
        guard let (request, zone) = effectiveHighlight,
              request.requestId != mapSession.lastFittedHighlightRequestId
        else { return }
        mapSession.isFollowing = false
        pendingCommand = .fitZone(zone.id)
        mapSession.lastFittedHighlightRequestId = request.requestId
    }
    #endif

    @MainActor
    private func resolveStyleURLIfNeeded() async {
        if styleURL != nil { return }
        isResolvingStyle = true
        defer { isResolvingStyle = false }
        let theme = currentEffectiveTheme()
        resolvedTheme = theme
        lastEvaluatedTheme = theme
        styleURL = await mapStyleURLProvider(theme)
    }

    @MainActor
    private func retryStyleLoad() async {
        isRetryingStyle = true
        defer { isRetryingStyle = false }
        // Reset flags so the MapLibreView re-attempts its style load once
        // we hand it a fresh URL (or the same URL — assigning clears the
        // flag regardless).
        styleLoadFailed = false
        isMapReady = false
        let theme = currentEffectiveTheme()
        let fresh = await mapStyleURLProvider(theme)
        if let fresh {
            resolvedTheme = theme
            lastEvaluatedTheme = theme
            // Assigning even the same URL forces updateUIView to re-evaluate;
            // MapLibre will retry the style fetch on the current view.
            styleURL = fresh
        }
    }

    @MainActor
    private func runSync() async {
        isSyncing = true
        defer { isSyncing = false }
        _ = await onSyncTap()
        // Re-attempt style resolution — a successful zone sync may have
        // coincided with the offline-bundle install finishing, and we also
        // want the MapLibre surface to re-evaluate once zones populate.
        styleLoadFailed = false
        isMapReady = false
        let theme = currentEffectiveTheme()
        resolvedTheme = theme
        lastEvaluatedTheme = theme
        styleURL = await mapStyleURLProvider(theme)
    }

    /// Computes the effective map theme using the user's mode + GPS + the
    /// minute-resolution wall clock. Symmetric ±0.5° hysteresis around the
    /// civil-twilight boundary suppresses flicker for users parked near
    /// the day/night seam — without it, sub-arcminute swings in the
    /// astronomical altitude can bounce the resolver across the gate.
    private func currentEffectiveTheme() -> MapTheme {
        let mode = settings.mapThemeMode
        if mode != .auto {
            return mode == .light ? .light : .dark
        }
        let position = tracking.currentPosition
        let lat = position?.lat ?? MapThemeResolver.fallbackLatSofia
        let lng = position?.lng ?? MapThemeResolver.fallbackLngSofia
        let altitudeDeg = MapThemeResolver.solarAltitudeDegrees(lat: lat, lng: lng, now: nowTick)
        let boundary = MapThemeResolver.civilTwilightAltitudeDeg
        switch resolvedTheme {
        case .light:
            return altitudeDeg < boundary - hysteresisMarginDeg ? .dark : .light
        case .dark:
            return altitudeDeg > boundary + hysteresisMarginDeg ? .light : .dark
        case nil:
            return altitudeDeg > boundary ? .light : .dark
        }
    }

    @MainActor
    private func reevaluateThemeIfNeeded() {
        let theme = currentEffectiveTheme()
        guard theme != resolvedTheme else {
            lastEvaluatedTheme = theme
            return
        }
        resolvedTheme = theme
        lastEvaluatedTheme = theme
        Task {
            isMapReady = false
            styleLoadFailed = false
            styleURL = await mapStyleURLProvider(theme)
        }
    }

    private var hysteresisMarginDeg: Double { 0.5 }
}
