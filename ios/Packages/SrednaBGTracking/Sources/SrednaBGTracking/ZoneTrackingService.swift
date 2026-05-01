// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import Observation
import SrednaBGCore
import SrednaBGData

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
    private var consumerTask: Task<Void, Never>?

    @ObservationIgnored
    private var currentIntervalMs: Int = AdaptiveLocationCadence.farIntervalMs

    public init(
        zones: [Zone],
        provider: any LocationProviding,
        alerts: AudioAlertManager,
        settings: SettingsStore
    ) {
        self.zones = zones
        self.detector = ZoneDetector(zones: zones)
        self.provider = provider
        self.alerts = alerts
        self.settings = settings
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
    }

    public func start() async {
        guard !isTracking else { return }
        isTracking = true

        let auth = await provider.authorization
        if auth == .notDetermined {
            await provider.requestAuthorization()
        } else if auth == .denied {
            isTracking = false
            return
        }

        do {
            try await provider.start()
        } catch {
            isTracking = false
            return
        }

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
        }

        // Fire-and-forget the TTS pipeline so we don't block the GPS consumer
        // on synthesis (could be hundreds of ms while the audio session
        // negotiates ducking).
        Task.detached { [alerts] in
            await alerts.handle(previous: previous, current: next, currentSpeedKmh: point.speed)
        }

        // Adjust GPS cadence as we move toward / into / out of zones.
        let desiredMs = AdaptiveLocationCadence.intervalMs(for: next, position: point, zones: zones)
        if desiredMs != currentIntervalMs {
            currentIntervalMs = desiredMs
            await provider.setIntervalMs(desiredMs)
        }
    }
}
