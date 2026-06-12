// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/**
 * Pins the zone-catalog gate the tracking service collects through —
 * mirror of the iOS `updateZonesAppliesContentOnlyChange` lifecycle test.
 * The old ID-set gate (`distinctUntilChangedBy { ids }`) swallowed a limit
 * change under a stable zone ID, so a synced update never reached a running
 * detector.
 */
class ZoneCatalogGateTest {

    @Test
    fun `content-only change under a stable id re-emits`() = runTest {
        val emissions = flowOf(
            listOf(makeZone(carLimit = 140)),
            listOf(makeZone(carLimit = 120)),
        ).distinctZoneCatalog().toList()

        assertEquals(2, emissions.size)
        assertEquals(120, emissions.last().single().speedLimits.car)
    }

    @Test
    fun `identical catalog is suppressed`() = runTest {
        val emissions = flowOf(
            listOf(makeZone(carLimit = 140)),
            listOf(makeZone(carLimit = 140)),
        ).distinctZoneCatalog().toList()

        assertEquals(1, emissions.size)
    }

    private fun makeZone(carLimit: Int) = Zone(
        id = "test-1",
        road = "Test Road",
        roadLatin = null,
        direction = "east",
        description = "Test",
        start = ZoneEndpoint(lat = 42.0, lng = 23.0),
        end = ZoneEndpoint(lat = 42.1, lng = 23.1),
        distanceM = 5000,
        speedLimits = SpeedLimits(car = carLimit, truck = 80, bus = 90),
        centerline = listOf(listOf(42.0, 23.0), listOf(42.1, 23.1)),
        source = "test",
        lastVerified = "2026-04-12",
    )
}
