// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

#if canImport(CoreLocation)
import Foundation
@preconcurrency import CoreLocation
import SrednaBGCore
import SrednaBGData

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
    private var requestedIntervalMs: Int = 1000
    private var lastForwardedMs: Int64 = 0

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
            lastForwardedMs = 0
            return prior
        }
        c?.finish()
    }

    /// Decides whether a fix arriving at `nowMs` should be forwarded given the
    /// timestamp of the last forwarded fix and the requested cadence. Returns
    /// `true` on the very first fix (`lastForwardedMs == 0`), on any fix that
    /// has waited at least `intervalMs - 200ms` since the previous forward,
    /// and on backward clock jumps (defensive — the wall clock can be
    /// adjusted by the system or NTP mid-drive). 200 ms of slack avoids
    /// drift-induced single-sample stalls when CoreLocation delivers fixes a
    /// touch faster than the requested cadence.
    static func shouldForward(nowMs: Int64, lastForwardedMs: Int64, intervalMs: Int) -> Bool {
        if lastForwardedMs == 0 { return true }
        let elapsed = nowMs - lastForwardedMs
        if elapsed < 0 { return true }
        let threshold = Int64(max(intervalMs - 200, 0))
        return elapsed >= threshold
    }

    public func setIntervalMs(_ ms: Int) async {
        // QA harness tripwire: line shape must match `qa/parsers.py` INTERVAL_RE.
        QALog.location.info("requestLocationWithInterval intervalMs=\(ms, privacy: .public)")
        // CoreLocation's `distanceFilter` is a *minimum-distance* gate, not a
        // time interval: setting it to 50m for the "far from zone" cadence
        // froze the speed display when the user stopped at a light, because
        // no fix is delivered until the device moves that far. Instead let
        // CoreLocation push fixes freely and throttle to the requested cadence
        // on the consumer side (`shouldForward` in `emit`).
        manager.distanceFilter = kCLDistanceFilterNone
        manager.desiredAccuracy = ms <= 1500
            ? kCLLocationAccuracyBestForNavigation
            : kCLLocationAccuracyBest
        lock.withLock {
            requestedIntervalMs = max(ms, 0)
        }
    }

    #if DEBUG
    public func injectDebugFix(lat: Double, lng: Double, speedMps: Double, bearing: Double?,
                               timestampMs: Int64?) async {
        let coord = CLLocationCoordinate2D(latitude: lat, longitude: lng)
        // `timestampMs` carries the harness's simulated timeline: under a
        // compressed drive the stamps run AHEAD of the wall clock, which is
        // what keeps the speed-inference dt realistic (without it, 4×-faster
        // wall delivery infers 4× the encoded speed and clamps at 250 km/h —
        // mirrors Android's FEED_POINT `time_ms` handling).
        let stamp = timestampMs.map { Date(timeIntervalSince1970: Double($0) / 1000.0) } ?? Date()
        let loc = CLLocation(
            coordinate: coord,
            altitude: 0,
            horizontalAccuracy: 5,
            verticalAccuracy: 5,
            course: bearing ?? -1,
            speed: speedMps,
            timestamp: stamp
        )
        // assumeFresh: the wall-clock age gate in `emit` would reject sim
        // stamps from the future; an injected fix is fresh by definition
        // (delivered the instant it was built) — Android equivalently keys
        // freshness off elapsedRealtime delivery age, not `location.time`.
        emit(location: loc, assumeFresh: true)
    }
    #endif

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
            emit(location: location)
        }
    }

    fileprivate func emit(location: CLLocation, assumeFresh: Bool = false) {
        // QA harness tripwire: line shape must match `qa/parsers.py` LOC_RE.
        QALog.location.info(
            "onLocation: lat=\(location.coordinate.latitude, privacy: .public) lng=\(location.coordinate.longitude, privacy: .public) speed=\(location.speed >= 0 ? location.speed : -1, privacy: .public) accuracy=\(location.horizontalAccuracy >= 0 ? location.horizontalAccuracy : -1, privacy: .public) provider=gps mock=false"
        )
        let nowMs = Int64(location.timestamp.timeIntervalSince1970 * 1000)
        let pass: Bool = lock.withLock {
            if Self.shouldForward(nowMs: nowMs, lastForwardedMs: lastForwardedMs, intervalMs: requestedIntervalMs) {
                lastForwardedMs = nowMs
                return true
            }
            return false
        }
        guard pass else { return }
        // CLLocationManager may deliver a cached "last known" fix as the
        // first update — possibly hundreds of meters off from the real
        // GPS lock. Seeding lastLat/Lng from such a fix would make the
        // next real fix's deltaM spurious, producing a phantom speed
        // that clamps the inferred reading at 250 km/h. 10 s mirrors
        // Android's MAX_FIX_AGE_MS (CoreLocation timestamps are wall-
        // clock, so compare to Date()).
        let ageS = Date().timeIntervalSince(location.timestamp)
        let freshFix = assumeFresh || (ageS >= 0 && ageS <= 10)
        let speedAccMps: Double? = location.speedAccuracy >= 0 ? location.speedAccuracy : nil
        let raw = RawLocationFix(
            lat: location.coordinate.latitude,
            lng: location.coordinate.longitude,
            course: location.course >= 0 ? location.course : nil,
            speedMps: location.speed >= 0 ? location.speed : nil,
            timestampMs: Int64(location.timestamp.timeIntervalSince1970 * 1000),
            accuracyM: location.horizontalAccuracy >= 0 ? location.horizontalAccuracy : nil,
            speedAccuracyMps: speedAccMps,
            freshFix: freshFix
        )
        let (point, hasBearing, cont) = lock.withLock {
            let (point, hasBearing) = builder.build(raw)
            return (point, hasBearing, continuation)
        }
        // Skip the publish until we have a real bearing — same rationale
        // as the Android `LocationTrackingService` early-return: a default
        // 0° heading would false-match a zone whose `polylineBearing`
        // happens to fall inside the 45° tolerance.
        guard hasBearing else { return }
        cont?.yield(point)
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
