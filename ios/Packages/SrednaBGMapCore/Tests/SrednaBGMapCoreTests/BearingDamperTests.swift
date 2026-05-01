// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

import Foundation
import Testing
@testable import SrednaBGMapCore

@Suite("BearingDamper")
struct BearingDamperTests {

    @Test("belowThresholdHolds")
    func belowThresholdHolds() {
        var damper = BearingDamper(initial: 42)
        #expect(damper.effectiveBearing == 42)
        damper.update(speedKmh: 3, bearingDegrees: 180)
        #expect(damper.effectiveBearing == 42)
        damper.update(speedKmh: 5, bearingDegrees: 180)
        // Exactly 5 km/h is NOT above threshold — mirrors Android's `>` check.
        #expect(damper.effectiveBearing == 42)
    }

    @Test("aboveThresholdUpdates")
    func aboveThresholdUpdates() {
        var damper = BearingDamper(initial: 0)
        damper.update(speedKmh: 5.5, bearingDegrees: 270)
        #expect(damper.effectiveBearing == 270)
        damper.update(speedKmh: 50, bearingDegrees: 91.5)
        #expect(damper.effectiveBearing == 91.5)
    }

    @Test("negativeBearingNormalizes")
    func negativeBearingNormalizes() {
        var damper = BearingDamper()
        damper.update(speedKmh: 10, bearingDegrees: -45)
        #expect(damper.effectiveBearing == 315)
    }

    @Test("wrappedBearingNormalizes")
    func wrappedBearingNormalizes() {
        var damper = BearingDamper()
        damper.update(speedKmh: 10, bearingDegrees: 725)
        // 725 mod 360 = 5
        #expect(abs(damper.effectiveBearing - 5) < 1e-9)
    }

    @Test("holdsLastValueAcrossStops")
    func holdsLastValueAcrossStops() {
        var damper = BearingDamper()
        damper.update(speedKmh: 20, bearingDegrees: 120)
        damper.update(speedKmh: 0, bearingDegrees: 50)   // traffic light
        damper.update(speedKmh: 1, bearingDegrees: 60)   // rolling forward
        #expect(damper.effectiveBearing == 120)
        damper.update(speedKmh: 30, bearingDegrees: 60)
        #expect(damper.effectiveBearing == 60)
    }
}
