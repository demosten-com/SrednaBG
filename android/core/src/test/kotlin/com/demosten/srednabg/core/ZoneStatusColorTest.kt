// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class ZoneStatusColorTest {

    private fun inZone(isOverLimit: Boolean): ZoneState.InZone {
        return ZoneState.InZone(
            zone = TRAKIYA_T10,
            entryTime = 0L,
            distanceTraveled = 0.0,
            speedStatus = SpeedStatus(
                avgSpeed = null,
                maxSpeedForRemainder = 140.0,
                distanceRemaining = TRAKIYA_T10.distanceM.toDouble(),
                timeRemaining = 0.0,
                isOverLimit = isOverLimit,
            ),
            distanceRemaining = TRAKIYA_T10.distanceM.toDouble(),
        )
    }

    @Test
    fun `green when within limit and not currently speeding`() {
        val state = inZone(isOverLimit = false)
        assertEquals(ZONE_COLOR_GREEN, zoneStatusColor(state, currentSpeedKmh = 130.0))
    }

    @Test
    fun `green when current speed unknown`() {
        val state = inZone(isOverLimit = false)
        assertEquals(ZONE_COLOR_GREEN, zoneStatusColor(state, currentSpeedKmh = null))
    }

    @Test
    fun `yellow when currently speeding but average still recoverable`() {
        val state = inZone(isOverLimit = false)
        // Trakiya car limit is 140 km/h; 160 > 140 → yellow.
        assertEquals(ZONE_COLOR_YELLOW, zoneStatusColor(state, currentSpeedKmh = 160.0))
    }

    @Test
    fun `red when running average is over limit`() {
        val state = inZone(isOverLimit = true)
        // Over-limit dominates regardless of current speed.
        assertEquals(ZONE_COLOR_RED, zoneStatusColor(state, currentSpeedKmh = 130.0))
        assertEquals(ZONE_COLOR_RED, zoneStatusColor(state, currentSpeedKmh = 200.0))
        assertEquals(ZONE_COLOR_RED, zoneStatusColor(state, currentSpeedKmh = null))
    }

    @Test
    fun `amber tier stays car-relative for a truck-limit zone`() {
        // Locks ISSUE-002: the amber threshold is keyed to zone.speedLimits.car
        // (140 on Trakiya), NOT the vehicle-resolved limit (truck = 90). A truck
        // doing 120 km/h with a still-recoverable average is GREEN — 120 is under
        // the car limit even though it's over the truck limit — and only crosses
        // to amber above 140. If anyone "fixes" the colour to the per-vehicle
        // limit, the 120 case flips to amber and this test fails.
        val state = inZone(isOverLimit = false)
        assertEquals(ZONE_COLOR_GREEN, zoneStatusColor(state, currentSpeedKmh = 120.0))
        assertEquals(ZONE_COLOR_YELLOW, zoneStatusColor(state, currentSpeedKmh = 160.0))
    }
}
