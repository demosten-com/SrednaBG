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

    @ObservationIgnored
    private let zoneStateSink: @Sendable (ZoneState, Double?) async -> Void

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

    @ObservationIgnored
    private var currentIntervalMs: Int = AdaptiveLocationCadence.farIntervalMs

    public init(
        zones: [Zone],
        provider: any LocationProviding,
        alerts: AudioAlertManager,
        settings: SettingsStore,
        zoneStateSink: @escaping @Sendable (ZoneState, Double?) async -> Void = { _, _ in },
        onSessionStart: @escaping @Sendable () async -> Void = {},
        onSessionStop: @escaping @Sendable () async -> Void = {}
    ) {
        self.zones = zones
        self.detector = ZoneDetector(zones: zones)
        self.provider = provider
        self.alerts = alerts
        self.settings = settings
        self.zoneStateSink = zoneStateSink
        self.onSessionStart = onSessionStart
        self.onSessionStop = onSessionStop
    }

    /// Replace the active zone catalog (e.g. after a successful sync). Resets
    /// the detector state — a partial traversal across an old/new zone diff
    /// is meaningless, so we pretend the user just opened the app.
    public func updateZones(_ newZones: [Zone]) {
        let same = newZones.map(\.id) == zones.map(\.id)
        guard !same else { return }
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
        guard !isTracking else { return }

        let resolved = await ensureAlwaysAuthorization()
        permission = resolved
        guard resolved == .always else { return }

        do {
            try await provider.start()
        } catch {
            return
        }

        isTracking = true

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
    }

    public func stop() async {
        consumerTask?.cancel()
        consumerTask = nil
        await provider.stop()
        await alerts.reset()
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

        // Fire-and-forget the TTS pipeline so we don't block the GPS consumer
        // on synthesis (could be hundreds of ms while the audio session
        // negotiates ducking).
        Task.detached { [alerts] in
            await alerts.handle(previous: previous, current: next, currentSpeedKmh: point.speed)
        }

        // Fire-and-forget the Live Activity update — the sink throttles
        // internally so calling on every point is safe.
        Task.detached { [zoneStateSink] in
            await zoneStateSink(next, point.speed)
        }

        // Adjust GPS cadence as we move toward / into / out of zones.
        let desiredMs = AdaptiveLocationCadence.intervalMs(for: next, position: point, zones: zones)
        if desiredMs != currentIntervalMs {
            currentIntervalMs = desiredMs
            await provider.setIntervalMs(desiredMs)
        }
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
    public func debugFeed(lat: Double, lng: Double, speedMps: Double, bearing: Double?) async {
        await provider.injectDebugFix(lat: lat, lng: lng, speedMps: speedMps, bearing: bearing)
    }
    #endif
}
