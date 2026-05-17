// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import SrednaBGCore

/// Abstraction over CoreLocation so tests can drive the tracking service
/// with scripted GPX traces (mirrors the `qa/` harness on Android). The real
/// implementation is in `LocationTracker` (iOS-only); tests use `MockLocationProvider`.
public protocol LocationProviding: Sendable {
    /// Resolved permission status. Optional — may be `unknown` on platforms
    /// without CoreLocation (e.g. macOS test runs).
    var authorization: LocationAuthorization { get async }

    /// Stream of GPS points. Cold by convention: subscribers should call
    /// `start()` to begin updates and `stop()` to cancel.
    func updates() async -> AsyncStream<GpsPoint>

    func start() async throws
    func stop() async
    func setIntervalMs(_ ms: Int) async

    /// Triggers the iOS location-permission prompt appropriate to the current
    /// state and returns the resolved authorization once the user answers (or
    /// immediately, if the state is already terminal). The two-step flow used
    /// by `ZoneTrackingService` calls this twice — once from `.notDetermined`
    /// to obtain When-In-Use, then again from `.authorizedWhenInUse` to drive
    /// the Always upgrade prompt.
    func requestAuthorization() async -> LocationAuthorization

    /// QA harness hook: synthesize a GPS fix and drive it through the
    /// provider's normal emission pipeline. Default implementation is a
    /// no-op; only the production `CLLocationTracker` overrides in DEBUG.
    func injectDebugFix(lat: Double, lng: Double, speedMps: Double, bearing: Double?) async
}

public enum LocationAuthorization: Sendable, Equatable {
    case unknown
    case notDetermined
    case denied
    case authorizedWhenInUse
    case authorizedAlways
}

public enum LocationProviderError: Error, Sendable {
    case authorizationDenied
    case unavailable
}

public extension LocationProviding {
    /// Default no-op. Only the production `CLLocationTracker` overrides this
    /// in DEBUG builds so the QA harness can drive synthetic GPS fixes
    /// through the exact same pipeline as real ones.
    func injectDebugFix(lat: Double, lng: Double, speedMps: Double, bearing: Double?) async {
        // no-op default
    }
}
