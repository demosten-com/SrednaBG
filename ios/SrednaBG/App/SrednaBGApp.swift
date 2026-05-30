// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBG

import SwiftUI
import SrednaBGCore
import SrednaBGData
import SrednaBGTracking
import SrednaBGMapCore
import SrednaBGUI

/// Top-level SwiftUI app. Composes the four packages, owns the long-lived
/// services as `@State`, and wires the SwiftUI view tree to `RootView`.
///
/// This file lives outside the SwiftPM manifest — it's the source for the
/// thin app shell `Xcode` target that bundles the SwiftPM packages into a
/// distributable `.app`. See `ios/README.md` for project-creation steps.
@main
struct SrednaBGApp: App {

    @State private var container: AppContainer

    init() {
        // The container constructor wires sync, settings, zones, tracking,
        // and audio together. Constructed once per process — main-actor
        // isolated so SwiftUI bindings work without `await`.
        let container = AppContainer()
        _container = State(initialValue: container)

        // Register both background tasks before scenes connect — Apple's
        // requirement (must happen during app launch, not later). Capture
        // the local `container` so the closures don't try to capture the
        // `App` struct's mutating `self` via `@State`.
        //
        // Map-sync is gated on `FeatureFlags.isMapSyncEnabled` (off until the
        // production backend serves `/api/map/bundle.zip` + `map_hash`). We
        // still register the identifier with BGTaskScheduler so any task
        // queued by a prior version completes via a no-op handler instead of
        // being treated as unhandled; we just never submit a new request.
        #if os(iOS)
        BackgroundSyncScheduler.register(
            zoneSync: { _ = await container.runZoneSync() },
            mapSync: {
                guard FeatureFlags.isMapSyncEnabled else { return }
                _ = await container.runMapSync()
            }
        )
        BackgroundSyncScheduler.scheduleZoneSync()
        if FeatureFlags.isMapSyncEnabled {
            BackgroundSyncScheduler.scheduleMapSync()
        }
        #endif

        // QA harness debug surface — see SrednaBGApp+DebugServer.swift.
        // Debug builds only; no-op in Release.
        #if DEBUG
        container.startDebugServer()
        #endif
    }

    var body: some Scene {
        WindowGroup {
            RootView(
                tracking: container.tracking,
                settings: container.settings,
                onSyncTap: { await container.runZoneSync() },
                mapStyleURLProvider: { theme in await container.mapStyleURL(for: theme) }
            )
            .task { await container.bootstrap() }
        }
    }
}

/// Single composition root. Construct once at process start; all services
/// are reachable through this object.
@MainActor
final class AppContainer {

    let settings: SettingsStore
    let tracking: ZoneTrackingService
    let zoneStore: ZoneStore
    let mapInstaller: OfflineMapInstaller
    let syncClient: SyncClient
    let alerts: AudioAlertManager

    // Lazily started the first time `mapStyleURL(for:)` sees an installed
    // bundle. Kept for the lifetime of the process so MapLibre's tile cache
    // doesn't churn when the user switches tabs. Rewrite output is cached
    // per theme — the rewriter writes `style.http.<theme>.json` once per
    // theme and reuses that URL on subsequent map mounts.
    private var tileServer: LocalTileServer?
    private var tileReader: MBTilesReader?
    private var cachedStyleURLs: [MapTheme: URL] = [:]

    #if DEBUG
    /// Owned by `startDebugServer()` (in `SrednaBGApp+DebugServer.swift`)
    /// so the QA loopback listener outlives any local scope. Stored
    /// properties must live in the class body, so this declaration stays
    /// here even though everything that touches it lives in the +Debug
    /// extension. Nil in non-debug builds.
    var debugServer: DebugControlServer?
    #endif

    init() {
        // Settings live in the standard `UserDefaults` so the app, the
        // future Widget extension, and the future debug `URL` handler can
        // all read the same values without an App Group.
        self.settings = SettingsStore()

        // Persistent zone cache + offline map under the app sandbox's
        // Application Support directory.
        let baseDir = (try? ZoneStore.defaultURL().deletingLastPathComponent())
            ?? FileManager.default.temporaryDirectory
        self.zoneStore = ZoneStore(url: baseDir.appendingPathComponent("zones.json"))
        self.mapInstaller = OfflineMapInstaller(rootDir: baseDir)

        // Backend host — both debug and release hit the Namecheap production
        // host so dev builds always exercise real zone data. Mirrors the
        // unified Android `ZONE_API_BASE_URL`.
        self.syncClient = SyncClient(urls: .production)

        let settings = self.settings
        let snapshotProvider: @Sendable () async -> SettingsSnapshot = {
            await MainActor.run {
                SettingsSnapshot(
                    voiceEnabled: settings.voiceEnabled,
                    periodicVoiceUpdates: settings.periodicVoiceUpdates,
                    announceOnlyWhenOver: settings.announceOnlyWhenOver,
                    vehicleType: settings.vehicleType,
                    appLanguage: settings.appLanguage
                )
            }
        }

        #if canImport(AVFoundation)
        let engine: any TTSEngine = AVSpeechTTSEngine()
        #else
        let engine: any TTSEngine = SilentTTSEngine()
        #endif
        self.alerts = AudioAlertManager(engine: engine, snapshot: snapshotProvider)

        #if os(iOS)
        let provider: any LocationProviding = CLLocationTracker()
        // The LiveActivityManager keeps an ActivityKit Live Activity in sync
        // with `ZoneState`. Beyond surfacing tracking on the Lock Screen, an
        // active Live Activity is what convinces iOS to keep the process
        // resident in the background for the duration of a drive — the
        // single biggest fix for "GPS stopped while screen was locked".
        //
        // The activity is created at session start (foreground-only — Apple
        // rejects `Activity.request` from the background) and torn down at
        // session stop. Per-zone updates flow through the regular sink while
        // the activity is alive.
        let liveActivity = LiveActivityManager()
        let zoneStateSink: @Sendable (ZoneState, Double?) async -> Void = { state, speed in
            await liveActivity.update(state: state, currentSpeedKmh: speed)
        }
        let onSessionStart: @Sendable () async -> Void = {
            await liveActivity.sessionStart()
        }
        let onSessionStop: @Sendable () async -> Void = {
            await liveActivity.sessionStop()
        }
        #else
        let provider: any LocationProviding = SilentLocationProvider()
        let zoneStateSink: @Sendable (ZoneState, Double?) async -> Void = { _, _ in }
        let onSessionStart: @Sendable () async -> Void = {}
        let onSessionStop: @Sendable () async -> Void = {}
        #endif
        self.tracking = ZoneTrackingService(
            zones: [],
            provider: provider,
            alerts: alerts,
            settings: settings,
            zoneStateSink: zoneStateSink,
            onSessionStart: onSessionStart,
            onSessionStop: onSessionStop
        )
    }

    /// Hydrate from disk (then attempt a fresh sync in the background) so the
    /// app comes up with last-known zones immediately.
    func bootstrap() async {
        await zoneStore.loadFromDisk()
        let cached = await zoneStore.snapshot()
        if cached.isEmpty {
            // First-launch fallback: parse the bundled `bundled-zones.json`.
            if let response = BundledZonesLoader().load() {
                try? await zoneStore.replaceAll(with: response.zones)
                tracking.updateZones(response.zones)
                settings.cachedZoneHash = response.hash
            }
        } else {
            tracking.updateZones(cached)
        }

        // Bootstrap the offline map from the in-app bundle if present.
        if let bundleSource = Bundle.main.url(forResource: "OfflineMap", withExtension: nil) {
            try? await mapInstaller.installFromBundle(bundleSource)
        }

        // Kick off initial zone + map syncs, fire-and-forget. Mirrors the
        // Android app scheduling both `ZoneSyncWorker` and `MapSyncWorker` —
        // iOS `BGAppRefreshTask` / `BGProcessingTask` are best-effort, so we
        // also run them on launch to guarantee a hash-gated check per session.
        // Map sync is gated on `FeatureFlags.isMapSyncEnabled` — see QAFlags.swift.
        Task { _ = await runZoneSync() }
        if FeatureFlags.isMapSyncEnabled {
            Task { _ = await runMapSync() }
        }
    }

    func runZoneSync() async -> SyncResult {
        do {
            let version = try await syncClient.fetchVersion()
            if !settings.cachedZoneHash.isEmpty, version.hash == settings.cachedZoneHash {
                return .upToDate
            }
            let response = try await syncClient.fetchZones()
            try await zoneStore.replaceAll(with: response.zones)
            tracking.updateZones(response.zones)
            settings.cachedZoneHash = response.hash
            return .updated
        } catch {
            return .failed(SyncFailure(underlying: error))
        }
    }

    func runMapSync() async -> SyncResult {
        do {
            let version = try await syncClient.fetchVersion()
            guard let remoteHash = version.mapHash, !remoteHash.isEmpty else {
                return .upToDate
            }
            if !settings.cachedMapHash.isEmpty, remoteHash == settings.cachedMapHash {
                return .upToDate
            }
            let zipDest = FileManager.default.temporaryDirectory
                .appendingPathComponent("map-bundle-\(UUID().uuidString).zip")
            _ = try await syncClient.downloadMapBundle(to: zipDest)
            defer { try? FileManager.default.removeItem(at: zipDest) }
            try await mapInstaller.installDownloadedBundle(zipDest)
            settings.cachedMapHash = remoteHash
            // Invalidate cached rewrites — on-disk mbtiles was swapped.
            cachedStyleURLs.removeAll()
            return .updated
        } catch {
            return .failed(SyncFailure(underlying: error))
        }
    }

    /// Resolves the MapLibre style URL used by `ZoneMapScreen` for the
    /// requested theme. Prefers the on-disk offline bundle (served through
    /// the loopback tile server), falls back to the network style when the
    /// bundle isn't installed (first-launch race, missing `OfflineMap/` Run
    /// Script, or corrupted bundle). MapLibre reports a delegate failure if
    /// the network style is also unreachable; `ZoneMapScreen` shows the
    /// retry-sync empty state in that case.
    ///
    /// The dark style only ships in the bundle, so the network fallback is
    /// always the (light) `mapStyleFallbackURL` regardless of the requested
    /// theme — acceptable because the fallback only fires on first launch
    /// before the bundle finishes installing.
    func mapStyleURL(for theme: MapTheme) async -> URL? {
        if let cached = cachedStyleURLs[theme] { return cached }
        if await mapInstaller.isInstalled() {
            do {
                let url = try await ensureTileServerAndRewrite(for: theme)
                cachedStyleURLs[theme] = url
                return url
            } catch {
                // fall through to network fallback
            }
        }
        return syncClient.urls.mapStyleFallbackURL
    }

    private func ensureTileServerAndRewrite(for theme: MapTheme) async throws -> URL {
        let layout = mapInstaller.layout
        if tileReader == nil {
            tileReader = try MBTilesReader(path: layout.mbtilesURL.path)
        }
        guard let tileReader else { throw MapStyleError.readerMissing }

        let server: LocalTileServer
        if let existing = tileServer {
            server = existing
        } else {
            server = LocalTileServer(reader: tileReader)
            tileServer = server
        }
        _ = try await server.start()
        guard let template = server.tileURLTemplate else {
            throw MapStyleError.serverTemplateMissing
        }

        // Read min/max zoom from the mbtiles metadata so MapLibre doesn't ask
        // for tiles outside the bundle's range (everything below minzoom
        // would return 204 and leave the viewport unrenderable).
        let minZoomStr = await tileReader.metadata("minzoom")
        let maxZoomStr = await tileReader.metadata("maxzoom")
        let minZoom = minZoomStr.flatMap(Int.init) ?? 0
        let maxZoom = maxZoomStr.flatMap(Int.init) ?? 14

        // Runtime paths — must be re-derived every launch. The iOS data
        // container UUID can change (reinstall, simulator state rotation, OS
        // restore), so baking `file://` paths into the on-disk style file is
        // a latent bug that resurfaces the moment the UUID moves. The
        // bundled style is a raw placeholder template; we substitute here.
        let mbtilesURI = "mbtiles://" + layout.mbtilesURL.path
        let glyphsURI = "file://" + layout.fontsURL.path
        let spriteURI = "file://" + layout.spriteBaseURL.path

        let original = try Data(contentsOf: layout.styleURL(for: theme))
        let rewritten = try StyleRewriter.rewriteMbtilesToHTTP(
            styleData: original,
            tileTemplate: template,
            mbtilesURI: mbtilesURI,
            glyphsURI: glyphsURI,
            spriteURI: spriteURI,
            defaultMinZoom: minZoom,
            defaultMaxZoom: maxZoom
        )
        // One rewritten output per theme so swapping themes at runtime
        // doesn't trash the other variant's cached file.
        let outputName = "style.http.\(theme.rawValue).json"
        let output = layout.mapDir.appendingPathComponent(outputName)
        try rewritten.write(to: output, options: .atomic)
        return output
    }

    enum MapStyleError: Error {
        case readerMissing
        case serverTemplateMissing
    }
}

/// Stand-in for `Sendable Error` wrapping in `SyncResult.failed(...)`.
struct SyncFailure: Error, Sendable, CustomStringConvertible {
    let description: String
    init(underlying: any Error) {
        self.description = String(describing: underlying)
    }
}

#if !os(iOS)
// macOS preview / `swift test` paths — neither CoreLocation background updates
// nor `AVAudioSession` configuration are available, so swap in silent stubs so
// the rest of the wiring still compiles.

struct SilentLocationProvider: LocationProviding {
    var authorization: LocationAuthorization { get async { .unknown } }
    func updates() async -> AsyncStream<GpsPoint> { AsyncStream { _ in } }
    func start() async throws {}
    func stop() async {}
    func setIntervalMs(_ ms: Int) async {}
    func requestAuthorization() async -> LocationAuthorization { .unknown }
}

struct SilentTTSEngine: TTSEngine {
    func speak(_ phrase: String, language: AppLanguage) async {}
    func stop() async {}
}
#endif
