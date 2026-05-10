// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

#if canImport(CoreLocation)
import Foundation
@preconcurrency import CoreLocation
import SrednaBGCore

/// Production `LocationProviding` backed by `CLLocationManager`.
///
/// Background-tracking caveats (see Apple "Handling location updates in the
/// background"):
///   * `allowsBackgroundLocationUpdates = true` requires `location` in
///     `UIBackgroundModes` (Info.plist) — wired in `App/Info.plist`.
///   * Deliberately **not** using iOS 17's `CLLocationUpdate.liveUpdates()`.
///     That API stops delivering when the app backgrounds unless a Live
///     Activity is also running; the classic delegate path keeps tracking
///     alive in the dash-mounted use case where the screen may be off.
///   * `pausesLocationUpdatesAutomatically = false` so the system doesn't
///     decide we're "stationary" while sitting at a red light inside a zone.
///   * Authorization uses a two-step flow — `requestAuthorization()` triggers
///     `requestWhenInUseAuthorization()` from `.notDetermined` and only
///     `requestAlwaysAuthorization()` from `.authorizedWhenInUse`. iOS 13+
///     refuses to surface the "Always" option on the first prompt; the second
///     call after a When-In-Use grant is what surfaces it.
public final class CLLocationTracker: NSObject, LocationProviding, @unchecked Sendable {

    private let manager = CLLocationManager()
    private let lock = NSLock()
    private var continuation: AsyncStream<GpsPoint>.Continuation?
    private var stream: AsyncStream<GpsPoint>?
    private var builder = GpsPointBuilder()
    private var authContinuation: CheckedContinuation<LocationAuthorization, Never>?

    public override init() {
        super.init()
        manager.delegate = self
        manager.allowsBackgroundLocationUpdates = true
        manager.pausesLocationUpdatesAutomatically = false
        manager.activityType = .automotiveNavigation
        manager.distanceFilter = kCLDistanceFilterNone
        manager.desiredAccuracy = kCLLocationAccuracyBest
    }

    public var authorization: LocationAuthorization {
        get async { Self.map(manager.authorizationStatus) }
    }

    public func updates() async -> AsyncStream<GpsPoint> {
        lock.withLock {
            if let stream { return stream }
            let (s, c) = AsyncStream<GpsPoint>.makeStream(bufferingPolicy: .bufferingNewest(8))
            stream = s
            continuation = c
            return s
        }
    }

    public func start() async throws {
        // Idempotent: if the caller never called `updates()` first, prepare
        // the stream so updates aren't dropped on the floor.
        _ = await updates()
        manager.startUpdatingLocation()
    }

    public func stop() async {
        manager.stopUpdatingLocation()
        let c: AsyncStream<GpsPoint>.Continuation? = lock.withLock {
            let prior = continuation
            continuation = nil
            stream = nil
            builder.reset()
            return prior
        }
        c?.finish()
    }

    public func setIntervalMs(_ ms: Int) async {
        // Map the requested cadence to a CoreLocation distance filter. The
        // delegate is still called more often than the time interval; we
        // throttle on the consumer side via `GpsPointBuilder.filter` and the
        // ZoneDetector's idempotency.
        let filter: Double
        switch ms {
        case ..<1500: filter = 5
        case 1500..<3500: filter = 15
        default: filter = 50
        }
        manager.distanceFilter = filter
        manager.desiredAccuracy = ms <= 1500
            ? kCLLocationAccuracyBestForNavigation
            : kCLLocationAccuracyBest
    }

    public func requestAuthorization() async -> LocationAuthorization {
        let current = manager.authorizationStatus
        switch current {
        case .notDetermined:
            return await awaitAuthChange { [manager] in
                manager.requestWhenInUseAuthorization()
            }
        case .authorizedWhenInUse:
            return await awaitAuthChange { [manager] in
                manager.requestAlwaysAuthorization()
            }
        default:
            // Already terminal (`.denied`, `.restricted`, `.authorizedAlways`):
            // iOS won't show another prompt — return the current state.
            return Self.map(current)
        }
    }

    private func awaitAuthChange(_ trigger: @Sendable () -> Void) async -> LocationAuthorization {
        await withCheckedContinuation { (cont: CheckedContinuation<LocationAuthorization, Never>) in
            // Replace any prior continuation. Only one prompt is in flight at
            // a time per Apple's UI; if the previous caller is still waiting,
            // resume it with the current state so it can fall through.
            let prior: CheckedContinuation<LocationAuthorization, Never>? = lock.withLock {
                let p = authContinuation
                authContinuation = cont
                return p
            }
            prior?.resume(returning: Self.map(manager.authorizationStatus))
            trigger()
        }
    }

    private static func map(_ status: CLAuthorizationStatus) -> LocationAuthorization {
        switch status {
        case .notDetermined: return .notDetermined
        case .denied, .restricted: return .denied
        case .authorizedWhenInUse: return .authorizedWhenInUse
        case .authorizedAlways: return .authorizedAlways
        @unknown default: return .unknown
        }
    }
}

extension CLLocationTracker: CLLocationManagerDelegate {

    public func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        for location in locations {
            let raw = RawLocationFix(
                lat: location.coordinate.latitude,
                lng: location.coordinate.longitude,
                course: location.course >= 0 ? location.course : nil,
                speedMps: location.speed >= 0 ? location.speed : nil,
                timestampMs: Int64(location.timestamp.timeIntervalSince1970 * 1000),
                accuracyM: location.horizontalAccuracy >= 0 ? location.horizontalAccuracy : nil
            )
            let (point, hasBearing, cont) = lock.withLock {
                let (point, hasBearing) = builder.build(raw)
                return (point, hasBearing, continuation)
            }
            // Skip the publish until we have a real bearing — same rationale
            // as the Android `LocationTrackingService` early-return: a default
            // 0° heading would false-match a zone whose `polylineBearing`
            // happens to fall inside the 45° tolerance.
            guard hasBearing else { continue }
            cont?.yield(point)
        }
    }

    public func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Transient errors are normal; the system will retry. Permanent
        // failures arrive via `locationManagerDidChangeAuthorization`.
    }

    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let mapped = Self.map(manager.authorizationStatus)

        // Resume any in-flight `requestAuthorization()` caller waiting on the
        // user's prompt response.
        let pending: CheckedContinuation<LocationAuthorization, Never>? = lock.withLock {
            let prior = authContinuation
            authContinuation = nil
            return prior
        }
        pending?.resume(returning: mapped)

        if mapped == .denied {
            let c: AsyncStream<GpsPoint>.Continuation? = lock.withLock {
                let prior = continuation
                continuation = nil
                stream = nil
                return prior
            }
            c?.finish()
        }
    }
}
#endif
