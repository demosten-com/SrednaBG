// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import Observation
import os
import SrednaBGCore
import SrednaBGData

/// Resolved location-permission state from the user's point of view. Drives
/// both the tracking gate (only `.always` allows updates to start) and the
/// HomeScreen permission card.
public enum LocationPermission: Sendable, Equatable {
    /// Initial state — no prompt has been answered yet.
    case unknown
    /// User granted "Always" — background tracking will work even after
    /// the system suspends the app.
    case always
    /// User granted "When In Use" but rejected the Always upgrade. Background
    /// updates would degrade silently (no relaunch on suspension), so we
    /// refuse to start.
    case whenInUse
    /// User denied or the device is restricted. Settings is the only path back.
    case denied
}

/// Single source of truth for tracking state. Owns the value-type
/// `ZoneDetector`, consumes the GPS stream, and publishes the live `ZoneState`
/// to SwiftUI via `@Observable`.
///
/// Pinned to `@MainActor` so SwiftUI views can read its properties without
/// `await`. The GPS-consumer task is started on `start()` and torn down by
/// `stop()`. Per the plan: never `await` longer than ~50 ms inside the
/// consumer loop — TTS and sync calls are dispatched without awaiting.
@Observable
@MainActor
public final class ZoneTrackingService {

    public private(set) var zoneState: ZoneState = .outside
    public private(set) var currentPosition: GpsPoint?
    public private(set) var isTracking: Bool = false
    public private(set) var permission: LocationPermission = .unknown

    @ObservationIgnored
    private var detector: ZoneDetector

    public private(set) var zones: [Zone]

    @ObservationIgnored
    private let provider: any LocationProviding

    @ObservationIgnored
    private let alerts: AudioAlertManager

    @ObservationIgnored
    private let settings: SettingsStore

    /// Receives every `ZoneState` transition together with the current speed
    /// and the vehicle-type-resolved speed limit for the active zone (nil
    /// outside zones). The limit is resolved here — the only place that has
    /// both the zone and the user's vehicle setting — so downstream surfaces
    /// (Live Activity) can't fall back to the car limit by accident.
    @ObservationIgnored
    private let zoneStateSink: @Sendable (ZoneState, Double?, Int?) async -> Void

    /// Fired once when tracking starts. Wired in `SrednaBGApp` to
    /// `LiveActivityManager.sessionStart()` — Apple's API requires
    /// `Activity.request` to run from the foreground, and `start()` is
    /// always called from a foreground tap on the Home screen.
    @ObservationIgnored
    private let onSessionStart: @Sendable () async -> Void

    /// Fired once when tracking stops, replacing the prior
    /// `zoneStateSink(.outside, nil)` end-signal.
    @ObservationIgnored
    private let onSessionStop: @Sendable () async -> Void

    @ObservationIgnored
    private var consumerTask: Task<Void, Never>?

    /// Reentrancy guard for `start()`: the method suspends several times
    /// before `isTracking` flips, and `@MainActor` reentrancy means a second
    /// Start tap could otherwise run the whole flow again — leaking the first
    /// consumer task and double-starting the Live Activity.
    @ObservationIgnored
    private var isStarting = false

    /// Periodic fallback timer: fires the auto-stop check even when no GPS
    /// fixes are arriving (e.g. iOS defers location updates while the device
    /// is stationary). The on-fix check inside `process(point:)` covers the
    /// fast path; this Task guarantees the threshold eventually fires.
    @ObservationIgnored
    private var autoStopTask: Task<Void, Never>?

    @ObservationIgnored
    private var currentIntervalMs: Int = AdaptiveLocationCadence.farIntervalMs

    /// Monotonic wall-clock stamp of the last "activity" — tracking start or
    /// a zone state-case transition. Compared against `settings.autoStopHours`
    /// on every GPS fix; when exceeded, `process(point:)` stops tracking so a
    /// forgotten-in-background app doesn't drain the battery.
    @ObservationIgnored
    private var lastActivityDate: Date = .distantPast

    /// Captures completed traversals for the History tab. Nil disables history
    /// (macOS / tests). Runs on this actor so its sample buffer needs no lock.
    @ObservationIgnored
    private let historyRecorder: HistoryRecorder?

    public init(
        zones: [Zone],
        provider: any LocationProviding,
        alerts: AudioAlertManager,
        settings: SettingsStore,
        historyRecorder: HistoryRecorder? = nil,
        zoneStateSink: @escaping @Sendable (ZoneState, Double?, Int?) async -> Void = { _, _, _ in },
        onSessionStart: @escaping @Sendable () async -> Void = {},
        onSessionStop: @escaping @Sendable () async -> Void = {}
    ) {
        self.zones = zones
        self.detector = ZoneDetector(zones: zones)
        self.provider = provider
        self.alerts = alerts
        self.settings = settings
        self.historyRecorder = historyRecorder
        self.zoneStateSink = zoneStateSink
        self.onSessionStart = onSessionStart
        self.onSessionStop = onSessionStop
    }

    /// Replace the active zone catalog (e.g. after a successful sync). Resets
    /// the detector state — a partial traversal across an old/new zone diff
    /// is meaningless, so we pretend the user just opened the app.
    ///
    /// Full-content comparison, not just IDs: the sync path is hash-gated
    /// upstream, so by the time this is called the content *did* change —
    /// a zone whose limit or centerline moved under a stable ID must still
    /// reach the running detector and map.
    public func updateZones(_ newZones: [Zone]) {
        guard newZones != zones else { return }
        zones = newZones
        detector = ZoneDetector(zones: newZones)
        zoneState = .outside
        // QA harness tripwire: line shape must match `qa/parsers.py` ZONES_RE.
        QALog.location.info("zones changed (n=\(newZones.count, privacy: .public))")
    }

    /// Re-read authorization from the system. Call when the app returns to
    /// foreground so the UI reflects changes the user made in Settings while
    /// the app was suspended.
    public func refreshPermission() async {
        let current = await provider.authorization
        permission = Self.map(current)
    }

    /// Drive the two-step authorization flow and start tracking if (and only
    /// if) the user granted Always. Refuses to start otherwise — the
    /// HomeScreen surfaces the resulting `permission` and offers Settings as
    /// the recovery path.
    public func start() async {
        guard !isTracking, !isStarting else { return }
        isStarting = true
        defer { isStarting = false }

        let resolved = await ensureAlwaysAuthorization()
        permission = resolved
        guard resolved == .always else { return }

        do {
            try await provider.start()
        } catch {
            return
        }

        isTracking = true
        lastActivityDate = Date()
        // Re-arm the announcement pipeline — a prior stop left it suppressed.
        await alerts.resume()

        // Create the Live Activity *before* the consumer task starts so the
        // first GPS point lands on a live activity. Must happen here while
        // we're still on a foreground call stack — `Activity.request` is
        // rejected from the background.
        await onSessionStart()

        let stream = await provider.updates()
        let initialMs = currentIntervalMs
        await provider.setIntervalMs(initialMs)

        consumerTask = Task { [weak self] in
            for await point in stream {
                guard let self else { break }
                await self.process(point: point)
            }
        }

        autoStopTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                try? await Task.sleep(nanoseconds: self.autoStopCheckIntervalNs())
                guard let strong = self as ZoneTrackingService? else { return }
                if strong.checkAutoStop() { return }
            }
        }
    }

    public func stop() async {
        consumerTask?.cancel()
        consumerTask = nil
        autoStopTask?.cancel()
        autoStopTask = nil
        // Silence TTS first so any in-flight announcement is cut off
        // immediately on Stop, before we tear down the location pipeline.
        await alerts.reset()
        await provider.stop()
        // End the Live Activity for this session. The sink no longer carries
        // the lifecycle signal — `onSessionStop` is the explicit hook.
        await onSessionStop()
        detector.reset()
        isTracking = false
        zoneState = .outside
        currentPosition = nil
    }

    private func process(point: GpsPoint) async {
        currentPosition = point

        let vehicleType = settings.vehicleType
        let previous = detector.state
        let next = detector.update(point, vehicleType: vehicleType)
        if next != zoneState {
            zoneState = next
            // QA harness tripwire: line shape must match `qa/parsers.py` STATE_RE.
            let zoneId = Self.zoneIdLabel(for: next)
            let speedLabel = String(format: "%.1f", point.speed)
            QALog.tts.info(
                "onZoneStateChanged prev=\(Self.stateName(previous), privacy: .public) new=\(Self.stateName(next), privacy: .public) zone=\(zoneId, privacy: .public) speed=\(speedLabel, privacy: .public)"
            )
        }
        if Self.stateName(previous) != Self.stateName(next) {
            lastActivityDate = Date()
        }
        if checkAutoStop() { return }

        let limitKmh = Self.resolvedLimit(for: next, vehicleType: vehicleType)

        // Capture the traversal for the History tab: buffers one SpeedSample
        // per in-zone fix and finalizes on the exit transition. Runs on this
        // actor, so its buffer needs no locking; the DB write hops off.
        historyRecorder?.onZoneStateChanged(
            point: point, previous: previous, next: next,
            vehicleType: vehicleType, limitKmh: limitKmh ?? 0
        )

        // Fire-and-forget the TTS pipeline so we don't block the GPS consumer
        // on synthesis (could be hundreds of ms while the audio session
        // negotiates ducking).
        Task.detached { [alerts] in
            await alerts.handle(previous: previous, current: next, currentSpeedKmh: point.speed)
        }

        // Fire-and-forget the Live Activity update — the sink throttles
        // internally so calling on every point is safe.
        Task.detached { [zoneStateSink] in
            await zoneStateSink(next, point.speed, limitKmh)
        }

        // Adjust GPS cadence as we move toward / into / out of zones.
        let desiredMs = AdaptiveLocationCadence.intervalMs(for: next, position: point, zones: zones)
        if desiredMs != currentIntervalMs {
            currentIntervalMs = desiredMs
            await provider.setIntervalMs(desiredMs)
        }
    }

    /// Returns true when auto-stop fired (caller should bail out of the
    /// current iteration). The actual `stop()` runs in a detached task so the
    /// hot path doesn't `await` on it.
    private func checkAutoStop() -> Bool {
        let thresholdS = autoStopThresholdSeconds()
        guard thresholdS.isFinite else { return false }
        let elapsedS = Date().timeIntervalSince(lastActivityDate)
        guard elapsedS > thresholdS else { return false }
        QALog.location.info(
            "auto-stop: idle for \(Int(elapsedS), privacy: .public)s (threshold=\(Int(thresholdS), privacy: .public)s) — stopping"
        )
        Task { @MainActor [weak self] in await self?.stop() }
        return true
    }

    private func autoStopThresholdSeconds() -> Double {
        if let debugSeconds = settings.debugAutoStopSeconds, debugSeconds > 0 {
            return Double(debugSeconds)
        }
        let hours = settings.autoStopHours
        return hours > 0 ? Double(hours) * 3600 : .infinity
    }

    /// Tighter cadence (1 s) when the debug seconds override is set so the QA
    /// scenario can complete in ~`debugSeconds + 1` s; otherwise 60 s.
    private func autoStopCheckIntervalNs() -> UInt64 {
        if let debugSeconds = settings.debugAutoStopSeconds,
           debugSeconds > 0, debugSeconds <= 60 {
            return 1_000_000_000
        }
        return 60_000_000_000
    }

    private func ensureAlwaysAuthorization() async -> LocationPermission {
        var current = await provider.authorization
        if current == .notDetermined {
            current = await provider.requestAuthorization()
        }
        if current == .authorizedWhenInUse {
            // Step 2 of Apple's two-prompt rule: the Always option only
            // surfaces in a second prompt issued from a When-In-Use state.
            current = await provider.requestAuthorization()
        }
        return Self.map(current)
    }

    private static func map(_ authz: LocationAuthorization) -> LocationPermission {
        switch authz {
        case .authorizedAlways: return .always
        case .authorizedWhenInUse: return .whenInUse
        case .denied: return .denied
        case .notDetermined, .unknown: return .unknown
        }
    }

    private static func resolvedLimit(for state: ZoneState, vehicleType: VehicleType) -> Int? {
        switch state {
        case .outside: return nil
        case .inZone(let inZone): return vehicleType.limit(inZone.zone.speedLimits)
        case .exiting(let exiting): return vehicleType.limit(exiting.zone.speedLimits)
        }
    }

    private static func stateName(_ s: ZoneState) -> String {
        switch s {
        case .outside: return "Outside"
        case .inZone: return "InZone"
        case .exiting: return "Exiting"
        }
    }

    private static func zoneIdLabel(for state: ZoneState) -> String {
        switch state {
        case .outside: return "-"
        case .inZone(let inZone): return inZone.zone.id
        case .exiting(let exiting): return exiting.zone.id
        }
    }

    #if DEBUG
    /// QA-only entry point for injecting a synthetic GPS fix that flows
    /// through the production `LocationProviding` pipeline.
    public func debugFeed(lat: Double, lng: Double, speedMps: Double, bearing: Double?,
                          timestampMs: Int64? = nil) async {
        await provider.injectDebugFix(lat: lat, lng: lng, speedMps: speedMps, bearing: bearing,
                                      timestampMs: timestampMs)
    }
    #endif
}
