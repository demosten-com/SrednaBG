// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Testing
@testable import SrednaBGCore

@Suite("ZoneStatusColor")
struct ZoneStatusColorTests {

    private func inZone(isOverLimit: Bool) -> ZoneState.InZone {
        ZoneState.InZone(
            zone: TRAKIYA_T10,
            entryTime: 0,
            distanceTraveled: 0,
            avgSpeed: nil,
            speedStatus: SpeedStatus(
                avgSpeed: nil,
                maxSpeedForRemainder: 140.0,
                distanceRemaining: Double(TRAKIYA_T10.distanceM),
                timeRemaining: 0,
                isOverLimit: isOverLimit
            ),
            distanceRemaining: Double(TRAKIYA_T10.distanceM)
        )
    }

    @Test
    func greenWhenWithinLimitAndNotCurrentlySpeeding() {
        let state = inZone(isOverLimit: false)
        #expect(zoneStatusColor(state: state, currentSpeedKmh: 130.0) == zoneColorGreen)
    }

    @Test
    func greenWhenCurrentSpeedUnknown() {
        let state = inZone(isOverLimit: false)
        #expect(zoneStatusColor(state: state, currentSpeedKmh: nil) == zoneColorGreen)
    }

    @Test
    func yellowWhenCurrentlySpeedingButAverageStillRecoverable() {
        let state = inZone(isOverLimit: false)
        // Trakiya car limit is 140 km/h; 160 > 140 → yellow.
        #expect(zoneStatusColor(state: state, currentSpeedKmh: 160.0) == zoneColorYellow)
    }

    @Test
    func redWhenRunningAverageIsOverLimit() {
        let state = inZone(isOverLimit: true)
        #expect(zoneStatusColor(state: state, currentSpeedKmh: 130.0) == zoneColorRed)
        #expect(zoneStatusColor(state: state, currentSpeedKmh: 200.0) == zoneColorRed)
        #expect(zoneStatusColor(state: state, currentSpeedKmh: nil) == zoneColorRed)
    }
}
