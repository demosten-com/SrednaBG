// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Testing
@testable import SrednaBGTracking

@Suite("BearingFallback")
struct BearingFallbackTests {

    @Test
    func validBearingPassesThrough() {
        var fb = BearingFallback()
        let b = fb.bearing(rawBearing: 87.0, lat: 42.0, lng: 23.0)
        #expect(b == 87.0)
        #expect(fb.lastBearing == 87.0)
    }

    @Test
    func negativeBearingFallsBackToNilWhenNoPriorPosition() {
        var fb = BearingFallback()
        let b = fb.bearing(rawBearing: -1, lat: 42.0, lng: 23.0)
        #expect(b == nil)
    }

    @Test
    func nilBearingDerivedFromPositionDeltaWhenMovedFarEnough() {
        var fb = BearingFallback()
        _ = fb.bearing(rawBearing: 12, lat: 42.0, lng: 23.0)
        // Move ~10m east — should derive ~90° bearing.
        let derived = fb.bearing(rawBearing: nil, lat: 42.0, lng: 23.0001)
        #expect(derived != nil)
        if let d = derived {
            #expect(d > 80 && d < 100, "Expected ~90°, got \(d)")
        }
    }

    @Test
    func nilBearingHoldsLastWhenMovedTooLittle() {
        var fb = BearingFallback()
        _ = fb.bearing(rawBearing: 87, lat: 42.0, lng: 23.0)
        // Move <5m — not enough to derive a fresh bearing; keep the prior.
        let held = fb.bearing(rawBearing: nil, lat: 42.0, lng: 23.00001)
        #expect(held == 87.0)
    }

    @Test
    func staleFixDoesNotSeedPosition() {
        var fb = BearingFallback()
        // A fresh fix seeds the position baseline.
        _ = fb.bearing(rawBearing: 12, lat: 42.0, lng: 23.0, freshFix: true)
        // A stale "last known" fix far away must NOT move the seed...
        _ = fb.bearing(rawBearing: nil, lat: 42.0, lng: 23.5, freshFix: false)
        #expect(fb.lastLat == 42.0)
        #expect(fb.lastLng == 23.0)
        // ...so the next fresh fix derives its bearing from the original
        // seed (~east), not from the bogus stale→fresh delta.
        let derived = fb.bearing(rawBearing: nil, lat: 42.0, lng: 23.0001, freshFix: true)
        #expect(derived != nil)
        if let d = derived {
            #expect(d > 80 && d < 100, "Expected ~90° from the un-corrupted seed, got \(d)")
        }
    }

    @Test
    func resetClearsState() {
        var fb = BearingFallback()
        _ = fb.bearing(rawBearing: 87, lat: 42.0, lng: 23.0)
        fb.reset()
        #expect(fb.lastBearing == nil)
        #expect(fb.lastLat == nil)
    }
}
