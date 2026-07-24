// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

// Debug-only: this dispatcher is reachable solely through `DebugControlServer`
// (also `#if DEBUG`). Gating it keeps the QA endpoint surface out of release.
#if DEBUG
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
        /// (lat, lng, speedMps, bearing, timestampMs). `timestampMs` is the
        /// harness's simulated-timeline stamp (epoch ms) — see `/inject`.
        public let feedLocation: @MainActor (Double, Double, Double, Double?, Int64?) -> Void
        /// Emit the QA `DUMP_HISTORY …` line (on tag `DebugSettings`) that the
        /// shared `qa/parsers.py` `HISTORY_DUMP_RE` matches — see `/history`.
        public let dumpHistory: @MainActor () -> Void
        /// Wipe the History store and refill it with `count` varied demo
        /// traversals; returns the number inserted — see `/history?action=seed`.
        public let seedHistory: @MainActor (Int) -> Int
        /// Wipe the History store — see `/history?action=clear`.
        public let clearHistory: @MainActor () -> Void

        public init(
            applySetting: @escaping @MainActor (String, String) -> Bool,
            runZoneSync: @escaping @MainActor () async -> DebugSyncOutcome,
            runMapSync: @escaping @MainActor () async -> DebugSyncOutcome,
            startTracking: @escaping @MainActor () async -> Void,
            stopTracking: @escaping @MainActor () async -> Void,
            feedLocation: @escaping @MainActor (Double, Double, Double, Double?, Int64?) -> Void = { _, _, _, _, _ in },
            dumpHistory: @escaping @MainActor () -> Void = {},
            seedHistory: @escaping @MainActor (Int) -> Int = { _ in 0 },
            clearHistory: @escaping @MainActor () -> Void = {}
        ) {
            self.applySetting = applySetting
            self.runZoneSync = runZoneSync
            self.runMapSync = runMapSync
            self.startTracking = startTracking
            self.stopTracking = stopTracking
            self.feedLocation = feedLocation
            self.dumpHistory = dumpHistory
            self.seedHistory = seedHistory
            self.clearHistory = clearHistory
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

        case "/inject":
            guard let latStr = params["lat"], let lat = Double(latStr),
                  let lngStr = params["lng"], let lng = Double(lngStr),
                  let speedStr = params["speed"], let speed = Double(speedStr)
            else {
                return Result(status: 400, body: "inject requires lat, lng, speed")
            }
            let bearing = params["bearing"].flatMap(Double.init)
            // Optional simulated-timeline stamp (epoch ms) — same name and
            // semantics as Android's FEED_POINT `time_ms` extra. Compressed
            // harness drives need it so the speed pipeline sees the encoded
            // cadence rather than the (faster) wall-clock injection rate.
            let timeMs = params["time_ms"].flatMap(Int64.init)
            handlers.feedLocation(lat, lng, speed, bearing, timeMs)
            return Result(status: 200, body: "ok")

        case "/history":
            return history(params)

        case "/tab":
            // Switch the RootView's TabView selection. Lets the screenshot
            // harness drive tab navigation over HTTP instead of needing a
            // mobile-mcp session to tap by accessibility id — iOS Simulator
            // has no `simctl`-level synthetic-tap path, so without this the
            // harness can't run standalone on iOS.
            guard let which = params["which"], DebugTabName.isValid(which) else {
                return Result(status: 400, body: "tab requires which in {home,map,settings}")
            }
            NotificationCenter.default.post(
                name: DebugTabName.selectionNotification,
                object: nil,
                userInfo: [DebugTabName.userInfoKey: which]
            )
            return Result(status: 200, body: "ok")

        default:
            return Result(status: 404, body: "no such endpoint: \(path)")
        }
    }

    /// History DB actions:
    ///   - `dump` — QA introspection: emit the `DUMP_HISTORY …` line (tag
    ///     `DebugSettings`) the shared parser matches (read + format + emit live
    ///     in the handler, which holds the store).
    ///   - `seed` — wipe and refill with `count` (default 12) varied demo
    ///     traversals so a developer can browse History scenarios without driving
    ///     every zone (the iOS peer of Android's QA-driven History fill).
    ///   - `clear` — wipe the store.
    ///   - `open` — push the newest record's detail page (screenshot harness).
    private func history(_ params: [String: String]) -> Result {
        switch params["action"] {
        case "dump":
            handlers.dumpHistory()
            return Result(status: 200, body: "ok")
        case "seed":
            let count = params["count"].flatMap(Int.init) ?? 12
            let inserted = handlers.seedHistory(count)
            return Result(status: 200, body: "seeded \(inserted)")
        case "clear":
            handlers.clearHistory()
            return Result(status: 200, body: "cleared")
        case "open":
            // Push a record's detail page — the screenshot harness's peer of
            // Android tapping the matching `history-row` node. `select` picks
            // newest (default) / first within-limit / first over-limit.
            let select = params["select"] ?? DebugHistoryOpen.newest
            NotificationCenter.default.post(
                name: DebugHistoryOpen.openNotification,
                object: nil,
                userInfo: [DebugHistoryOpen.selectUserInfoKey: select]
            )
            return Result(status: 200, body: "ok")
        default:
            return Result(status: 400, body: "history requires action in {dump,seed,clear,open}")
        }
    }
}
#endif
