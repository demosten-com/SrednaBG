// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBG

#if DEBUG
import Foundation
import SrednaBGCore
import SrednaBGData
import SrednaBGTracking

extension AppContainer {

    /// Spins up the QA harness's loopback HTTP debug server. Called once from
    /// `SrednaBGApp.init()` in Debug builds. Stores the server on
    /// `debugServer` so it outlives the local scope and stays alive for the
    /// lifetime of the process.
    ///
    /// Why HTTP instead of a `srednabg-debug://` URL scheme: `simctl openurl`
    /// pops an "Open in <App>" confirmation dialog on every dispatch, which
    /// makes automated QA runs unusable. Loopback HTTP avoids the prompt and
    /// returns a synchronous status code to the harness. The iOS Simulator
    /// shares the host's loopback, so the harness on macOS reaches the
    /// listener directly with no port forwarding.
    func startDebugServer() {
        let router = DebugActionRouter(handlers: debugHandlers())
        let server = DebugControlServer(router: router)
        debugServer = server
        Task { @MainActor in
            do {
                try await server.start()
            } catch {
                // Non-fatal: a stale simulator with the port already bound
                // (rare on a clean boot). The harness's /ping will time out
                // and surface the actual error.
            }
        }
    }

    /// Wires the container's services into the QA debug router. Each closure
    /// is `@MainActor`-isolated because the underlying `SettingsStore` and
    /// `ZoneTrackingService` both run on the main actor.
    private func debugHandlers() -> DebugActionRouter.Handlers {
        let settings = self.settings
        let tracking = self.tracking
        return DebugActionRouter.Handlers(
            applySetting: { key, value in applyDebugSetting(settings, key: key, value: value) },
            runZoneSync: { [weak self] in
                guard let self else { return .failed }
                switch await self.runZoneSync() {
                case .updated: return .updated
                case .upToDate: return .upToDate
                case .failed: return .failed
                }
            },
            runMapSync: { [weak self] in
                // Map sync is gated on FeatureFlags.isMapSyncEnabled (off until
                // the production backend serves the map bundle). The QA harness
                // talks to prod, so a debug-triggered sync against a backend
                // that can't fulfill it would only generate failure noise.
                guard FeatureFlags.isMapSyncEnabled else { return .upToDate }
                guard let self else { return .failed }
                switch await self.runMapSync() {
                case .updated: return .updated
                case .upToDate: return .upToDate
                case .failed: return .failed
                }
            },
            startTracking: { await tracking.start() },
            stopTracking: { await tracking.stop() },
            feedLocation: { lat, lng, speed, bearing, timeMs in
                Task { @MainActor in
                    await tracking.debugFeed(lat: lat, lng: lng, speedMps: speed,
                                             bearing: bearing, timestampMs: timeMs)
                }
            }
        )
    }
}

/// Free-function form of the settings dispatch so the closure inside
/// `debugHandlers()` stays under SwiftLint's function_body_length limit.
@MainActor
private func applyDebugSetting(_ settings: SettingsStore, key: String, value: String) -> Bool {
    let lower = value.lowercased()
    let asBool = (lower == "true" || lower == "1" || lower == "yes")
    switch key {
    case "voice_enabled": settings.voiceEnabled = asBool
    case "periodic_voice_updates": settings.periodicVoiceUpdates = asBool
    case "announce_only_when_over": settings.announceOnlyWhenOver = asBool
    case "app_language":
        guard let lang = AppLanguage(rawValue: value) else { return false }
        settings.appLanguage = lang
    case "vehicle_type":
        guard let v = VehicleType(rawValue: value) else { return false }
        settings.vehicleType = v
    case "alert_threshold_kmh":
        guard let n = Int(value) else { return false }
        settings.alertThresholdKmh = n
    case "map_heading_up":
        settings.mapHeadingUp = asBool
    case "map_theme_mode":
        // Android sends UPPERCASE enum names (AUTO/LIGHT/DARK) because its
        // MapThemeMode is a Kotlin enum with uppercase names; iOS's
        // MapThemeMode is a lowercase rawValue String enum. Lowercase
        // before init so the QA harness's single
        // `set_setting("map_theme_mode", ...)` call works on both platforms.
        guard let mode = MapThemeMode(rawValue: value.lowercased()) else { return false }
        settings.mapThemeMode = mode
    case "map_zoom_override":
        if value.isEmpty {
            settings.mapZoomOverride = nil
        } else if let zoom = Double(value) {
            settings.mapZoomOverride = (zoom == 0) ? nil : zoom
        } else {
            return false
        }
    case "debug_max_speed_override":
        if value.isEmpty {
            settings.debugMaxSpeedOverride = nil
        } else if let n = Int(value) {
            settings.debugMaxSpeedOverride = n
        } else {
            return false
        }
    case "auto_stop_hours":
        guard let n = Int(value) else { return false }
        settings.autoStopHours = n
    case "zone_sync_enabled":
        settings.zoneSyncEnabled = asBool
    case "cached_zone_hash":
        // QA poisons this to force the next manual sync into a full re-fetch
        // (mismatch → fetchZones) — mirrors Android's DebugControlReceiver.
        settings.cachedZoneHash = value
    case "cached_zone_version":
        settings.cachedZoneVersion = value
    case "cached_map_hash":
        settings.cachedMapHash = value
    case "debug_auto_stop_seconds":
        if value.isEmpty {
            settings.debugAutoStopSeconds = nil
        } else if let n = Int(value) {
            settings.debugAutoStopSeconds = (n > 0) ? n : nil
        } else {
            return false
        }
    default:
        return false
    }
    return true
}
#endif
