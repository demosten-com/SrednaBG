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

    @Test
    func amberTierStaysCarRelativeForATruckLimitZone() {
        // Locks ISSUE-002: the amber threshold is keyed to zone.speedLimits.car
        // (140 on Trakiya), NOT the vehicle-resolved limit (truck = 90). A truck
        // doing 120 km/h with a still-recoverable average is GREEN — 120 is under
        // the car limit even though it's over the truck limit — and only crosses
        // to amber above 140. If anyone "fixes" the colour to the per-vehicle
        // limit, the 120 case flips to amber and this test fails.
        let state = inZone(isOverLimit: false)
        #expect(zoneStatusColor(state: state, currentSpeedKmh: 120.0) == zoneColorGreen)
        #expect(zoneStatusColor(state: state, currentSpeedKmh: 160.0) == zoneColorYellow)
    }
}
