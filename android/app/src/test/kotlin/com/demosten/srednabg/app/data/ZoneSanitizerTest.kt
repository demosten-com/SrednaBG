// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class ZoneSanitizerTest {

    private fun zone(
        id: String = "i8-01-west",
        start: ZoneEndpoint = ZoneEndpoint(42.4606211, 23.803103),
        end: ZoneEndpoint = ZoneEndpoint(42.3793752, 23.8763595),
        distanceM: Int = 11440,
        limits: SpeedLimits = SpeedLimits(car = 90, truck = 80, bus = 80),
        centerline: List<List<Double>> = listOf(
            listOf(42.4606211, 23.803103),
            listOf(42.4200000, 23.840000),
            listOf(42.3793752, 23.8763595),
        ),
    ) = Zone(
        id = id,
        road = "Път I-8",
        direction = "west",
        description = "Ихтиман – Мирово",
        start = start,
        end = end,
        distanceM = distanceM,
        speedLimits = limits,
        centerline = centerline,
        source = "bgtoll+tolltracker",
        lastVerified = "2026-08-03",
    )

    @Test
    fun `a well-formed zone is usable and passes through unchanged`() {
        val z = zone()
        assertTrue(ZoneSanitizer.isUsable(z))
        assertEquals(z, ZoneSanitizer.withFallbackLimits(z))
    }

    // The exact shapes the 2026-08 Път I-8 merge failure put on the wire.

    @Test
    fun `an empty centerline is unusable`() {
        assertFalse(ZoneSanitizer.isUsable(zone(centerline = emptyList())))
    }

    @Test
    fun `a single-point centerline is unusable`() {
        val single = listOf(listOf(42.46, 23.80))
        assertFalse(ZoneSanitizer.isUsable(zone(centerline = single)))
    }

    @Test
    fun `placeholder zero-zero endpoints are unusable`() {
        assertFalse(ZoneSanitizer.isUsable(zone(start = ZoneEndpoint(0.0, 0.0))))
        assertFalse(ZoneSanitizer.isUsable(zone(end = ZoneEndpoint(0.0, 0.0))))
    }

    @Test
    fun `a non-positive distance is unusable`() {
        assertFalse(ZoneSanitizer.isUsable(zone(distanceM = 0)))
    }

    @Test
    fun `a missing car limit is unusable`() {
        assertFalse(ZoneSanitizer.isUsable(zone(limits = SpeedLimits(0, 80, 80))))
    }

    @Test
    fun `missing truck and bus limits fall back to the car limit`() {
        // Gson zero-fills the omitted fields; a 0 km_h limit would read as
        // permanently over-limit for that driver.
        val filled = ZoneSanitizer.withFallbackLimits(
            zone(limits = SpeedLimits(car = 90, truck = 0, bus = 0)),
        )
        assertEquals(90, filled.speedLimits.truck)
        assertEquals(90, filled.speedLimits.bus)
        assertEquals(90, filled.speedLimits.car)
    }

    @Test
    fun `an explicit motorcycle limit survives the fallback`() {
        val filled = ZoneSanitizer.withFallbackLimits(
            zone(limits = SpeedLimits(car = 90, truck = 0, bus = 0, motorcycle = 100)),
        )
        assertEquals(100, filled.speedLimits.motorcycle)
    }

    @Test
    fun `a repaired zone is reported, not silently accepted`() {
        // The shape that kills iOS 1.x outright and reads as a 0 km_h limit on
        // Android 1.x. This build survives it, so the only way QA can see it is
        // if the repair is reported.
        val result = ZoneSanitizer.sanitize(
            listOf(
                zone(id = "i8-01-north", limits = SpeedLimits(car = 90, truck = 0, bus = 0)),
                zone(id = "good-1"),
            ),
        )
        assertEquals(listOf("i8-01-north"), result.repairedIds)
        assertTrue(result.droppedIds.isEmpty())
        assertEquals(2, result.zones.size)
    }

    @Test
    fun `a complete zone is never reported as repaired`() {
        assertTrue(ZoneSanitizer.sanitize(listOf(zone())).repairedIds.isEmpty())
    }

    @Test
    fun `one bad zone costs one zone, not the whole catalog`() {
        val result = ZoneSanitizer.sanitize(
            listOf(
                zone(id = "good-1"),
                zone(id = "i8-02-east", start = ZoneEndpoint(0.0, 0.0), centerline = emptyList()),
                zone(id = "good-2"),
            ),
        )
        assertEquals(listOf("good-1", "good-2"), result.zones.map { it.id })
        assertEquals(listOf("i8-02-east"), result.droppedIds)
    }
}
