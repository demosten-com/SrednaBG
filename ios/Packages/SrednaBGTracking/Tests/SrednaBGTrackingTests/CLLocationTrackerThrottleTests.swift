// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

#if canImport(CoreLocation)
import Testing
@testable import SrednaBGTracking

/// Regression coverage for the consumer-side throttle that replaced
/// CoreLocation's `distanceFilter`. The distance filter froze the speed
/// display when the user stopped at a traffic light, because no fix is
/// delivered until the device moves a configured number of meters — the
/// Kalman filter never saw the "I'm stationary" measurement and held the
/// last value. The throttle keeps fix delivery time-based instead.
@Suite("CLLocationTracker throttle")
struct CLLocationTrackerThrottleTests {

    @Test
    func firstFixAlwaysForwards() {
        #expect(CLLocationTracker.shouldForward(nowMs: 1_000, lastForwardedMs: 0, intervalMs: 1_000))
        #expect(CLLocationTracker.shouldForward(nowMs: 0, lastForwardedMs: 0, intervalMs: 5_000))
    }

    @Test
    func dropsEarlyFix() {
        // 700ms after the last forward, with a 1s requested cadence and
        // 200ms slack — still under the 800ms threshold, so drop.
        #expect(!CLLocationTracker.shouldForward(nowMs: 1_700, lastForwardedMs: 1_000, intervalMs: 1_000))
    }

    @Test
    func forwardsWithinSlackWindow() {
        // 800ms == intervalMs - slack exactly; should pass.
        #expect(CLLocationTracker.shouldForward(nowMs: 1_800, lastForwardedMs: 1_000, intervalMs: 1_000))
        // Comfortably past the interval.
        #expect(CLLocationTracker.shouldForward(nowMs: 6_000, lastForwardedMs: 1_000, intervalMs: 5_000))
    }

    @Test
    func handlesBackwardClockJump() {
        // System clock / NTP adjusts backward mid-drive — never strand the
        // pipeline; forward immediately and let the next fix re-anchor.
        #expect(CLLocationTracker.shouldForward(nowMs: 500, lastForwardedMs: 1_000, intervalMs: 1_000))
    }

    @Test
    func zeroIntervalForwardsEveryFix() {
        // Defensive: if `setIntervalMs(0)` is ever called, throttle should
        // degrade to a no-op rather than rejecting every fix.
        #expect(CLLocationTracker.shouldForward(nowMs: 1_001, lastForwardedMs: 1_000, intervalMs: 0))
    }
}
#endif
