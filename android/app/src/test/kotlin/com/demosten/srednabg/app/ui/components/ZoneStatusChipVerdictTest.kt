// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.components

import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.VehicleType
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import com.demosten.srednabg.core.ZoneState
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * The exit verdict must judge the final average against the same
 * vehicle-type-resolved limit the engine used in-zone (ISSUE-002: it
 * previously compared against the car limit, so a truck averaging 100 in a
 * car-140/truck-90 zone exited with a green "OK").
 */
class ZoneStatusChipVerdictTest {

    private val zone = Zone(
        id = "maritsa-test-east",
        road = "АМ Марица",
        roadLatin = "Maritsa",
        direction = "east",
        description = "test",
        start = ZoneEndpoint(lat = 42.0, lng = 25.0),
        end = ZoneEndpoint(lat = 42.0, lng = 25.1),
        distanceM = 8000,
        speedLimits = SpeedLimits(car = 140, truck = 90, bus = 100, motorcycle = 120),
        centerline = listOf(listOf(42.0, 25.0), listOf(42.0, 25.1)),
        source = "test",
        lastVerified = "2026-06-10",
    )

    private fun exiting(finalAvg: Double?) = ZoneState.Exiting(zone, finalAvg)

    @Test
    fun `truck over its limit but under the car limit is over-limit`() {
        assertTrue(exitVerdictOverLimit(exiting(100.0), VehicleType.TRUCK))
    }

    @Test
    fun `car at the same average is within its limit`() {
        assertFalse(exitVerdictOverLimit(exiting(100.0), VehicleType.CAR))
    }

    @Test
    fun `motorcycle uses its explicit zone limit when present`() {
        assertTrue(exitVerdictOverLimit(exiting(130.0), VehicleType.MOTORCYCLE))
        assertFalse(exitVerdictOverLimit(exiting(130.0), VehicleType.CAR))
    }

    @Test
    fun `missing final average is not over-limit`() {
        assertFalse(exitVerdictOverLimit(exiting(null), VehicleType.TRUCK))
    }
}
