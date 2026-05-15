// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation

/// Dispatches debug actions to the right place inside the app. Used by
/// `DebugControlServer` (the loopback HTTP listener consumed by the QA
/// harness).
///
/// The router is on `@MainActor` so settings mutations and `SyncClient`
/// hops are safe. Concrete action handlers are passed in by the
/// `AppContainer` so this type stays free of UI/state imports.
@MainActor
public final class DebugActionRouter {

    public struct Handlers {
        public let applySetting: @MainActor (String, String) -> Bool
        public let runZoneSync: @MainActor () async -> DebugSyncOutcome
        public let runMapSync: @MainActor () async -> DebugSyncOutcome
        public let startTracking: @MainActor () async -> Void
        public let stopTracking: @MainActor () async -> Void

        public init(
            applySetting: @escaping @MainActor (String, String) -> Bool,
            runZoneSync: @escaping @MainActor () async -> DebugSyncOutcome,
            runMapSync: @escaping @MainActor () async -> DebugSyncOutcome,
            startTracking: @escaping @MainActor () async -> Void,
            stopTracking: @escaping @MainActor () async -> Void
        ) {
            self.applySetting = applySetting
            self.runZoneSync = runZoneSync
            self.runMapSync = runMapSync
            self.startTracking = startTracking
            self.stopTracking = stopTracking
        }
    }

    public struct Result {
        public let status: Int
        public let body: String
    }

    private let handlers: Handlers

    public init(handlers: Handlers) {
        self.handlers = handlers
    }

    /// `path` is the HTTP request path, e.g. `/setting`. `params` is the
    /// query string parsed into a dict.
    public func dispatch(path: String, params: [String: String]) async -> Result {
        switch path {
        case "/ping":
            return Result(status: 200, body: "pong")

        case "/setting":
            guard let key = params["key"], let value = params["value"] else {
                return Result(status: 400, body: "setting requires key and value")
            }
            let ok = handlers.applySetting(key, value)
            if ok {
                // QA harness tripwire: line shape must match `qa/parsers.py` SETTING_RE.
                QALog.settings.info("set \(key, privacy: .public)=\(value, privacy: .public)")
                return Result(status: 200, body: "ok")
            }
            return Result(status: 400, body: "unknown setting key")

        case "/sync":
            guard let action = params["action"] else {
                return Result(status: 400, body: "sync requires action")
            }
            let label = action == "zones" ? "SYNC_ZONES" : "SYNC_MAP"
            if QAFlags.networkOffline {
                DebugSyncHook.log(action: label, outcome: .failed, detail: "offline")
                return Result(status: 200, body: "Failed(offline)")
            }
            // Map sync is gated on FeatureFlags.isMapSyncEnabled (off until the
            // production backend serves the map bundle). Emit a "Skipped" line
            // mirroring Android's DebugSyncReceiver so the QA regression
            // scenario can assert the gate is in place on both platforms.
            if action == "map", !FeatureFlags.isMapSyncEnabled {
                QALog.sync.info(
                    "\(DebugSyncHook.actionPrefix, privacy: .public)\(label, privacy: .public) -> Skipped (feature disabled)"
                )
                return Result(status: 200, body: "Skipped(feature disabled)")
            }
            let outcome: DebugSyncOutcome
            switch action {
            case "zones": outcome = await handlers.runZoneSync()
            case "map": outcome = await handlers.runMapSync()
            default: return Result(status: 400, body: "unknown sync action")
            }
            DebugSyncHook.log(action: label, outcome: outcome, detail: nil)
            return Result(status: 200, body: outcome.rawValue)

        case "/tracking":
            guard let action = params["action"] else {
                return Result(status: 400, body: "tracking requires action")
            }
            // Fire-and-forget: `start()` chains through requestAuthorization
            // + Activity.request which can take a couple of seconds on the
            // simulator. The harness observes success via the GPS log stream,
            // not this response — so we return immediately to avoid blocking
            // the harness's HTTP timeout.
            let h = handlers
            switch action {
            case "start": Task { @MainActor in await h.startTracking() }
            case "stop": Task { @MainActor in await h.stopTracking() }
            default: return Result(status: 400, body: "unknown tracking action")
            }
            return Result(status: 200, body: "ok")

        case "/mute":
            QAFlags.ttsMuted = (params["on"] == "1" || params["on"] == "true")
            return Result(status: 200, body: QAFlags.ttsMuted ? "muted" : "unmuted")

        case "/network":
            QAFlags.networkOffline = (params["offline"] == "1" || params["offline"] == "true")
            return Result(status: 200, body: QAFlags.networkOffline ? "offline" : "online")

        default:
            return Result(status: 404, body: "no such endpoint: \(path)")
        }
    }
}
