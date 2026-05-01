// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.time.OffsetDateTime
import java.time.ZoneOffset

class MapThemeResolverTest {

    private fun utcMillis(year: Int, month: Int, day: Int, hour: Int, minute: Int = 0): Long =
        OffsetDateTime.of(year, month, day, hour, minute, 0, 0, ZoneOffset.UTC).toInstant().toEpochMilli()

    private fun sofiaPoint(): GpsPoint = GpsPoint(
        lat = 42.7, lng = 23.3, speed = 0.0, timestamp = 0L, bearing = 0.0,
    )

    @Test
    fun `manual LIGHT mode ignores time and position`() {
        val midnight = utcMillis(2026, 12, 21, 0)
        assertEquals(MapTheme.LIGHT, MapThemeResolver.resolve(MapThemeMode.LIGHT, sofiaPoint(), midnight))
    }

    @Test
    fun `manual DARK mode ignores time and position`() {
        val noon = utcMillis(2026, 6, 21, 12)
        assertEquals(MapTheme.DARK, MapThemeResolver.resolve(MapThemeMode.DARK, sofiaPoint(), noon))
    }

    @Test
    fun `auto noon summer Sofia is LIGHT`() {
        // 2026-06-21 12:00 UTC = 14:00 EEST in Sofia. Sun near maximum altitude.
        val t = utcMillis(2026, 6, 21, 12)
        assertEquals(MapTheme.LIGHT, MapThemeResolver.resolve(MapThemeMode.AUTO, sofiaPoint(), t))
    }

    @Test
    fun `auto local-midnight winter Sofia is DARK`() {
        // 2026-12-21 22:00 UTC = 00:00 EET in Sofia. Sun far below horizon.
        val t = utcMillis(2026, 12, 21, 22)
        assertEquals(MapTheme.DARK, MapThemeResolver.resolve(MapThemeMode.AUTO, sofiaPoint(), t))
    }

    @Test
    fun `auto with no GPS falls back to Sofia`() {
        val t = utcMillis(2026, 6, 21, 12)
        assertEquals(MapTheme.LIGHT, MapThemeResolver.resolve(MapThemeMode.AUTO, null, t))
    }

    @Test
    fun `auto deep night any Bulgaria position is DARK`() {
        val t = utcMillis(2026, 12, 21, 0) // 02:00 EET
        val varna = GpsPoint(lat = 43.21, lng = 27.91, speed = 0.0, timestamp = 0L, bearing = 0.0)
        assertEquals(MapTheme.DARK, MapThemeResolver.resolve(MapThemeMode.AUTO, varna, t))
    }

    @Test
    fun `solar altitude is positive at summer noon Sofia`() {
        val t = utcMillis(2026, 6, 21, 10) // ~ 12:00 EEST → near solar transit (~12:32 EEST in Sofia)
        val alt = MapThemeResolver.solarAltitudeDegrees(42.7, 23.3, t)
        assertTrue(alt > 65.0, "expected high altitude, got $alt")
    }

    @Test
    fun `solar altitude is well below horizon at winter midnight Sofia`() {
        val t = utcMillis(2026, 12, 21, 22) // local midnight Sofia
        val alt = MapThemeResolver.solarAltitudeDegrees(42.7, 23.3, t)
        assertTrue(alt < -50.0, "expected very negative altitude, got $alt")
    }

    @Test
    fun `boundary near civil twilight Sofia evening`() {
        // Around end of civil twilight (~30 min after sunset). Pick a
        // span that straddles the -6° boundary on the equinox so the
        // resolver flips from LIGHT → DARK as time advances.
        // 2026-09-23 in Sofia: sunset ~18:48 local (15:48 UTC), civil
        // twilight ends ~19:18 local (16:18 UTC).
        val brightAfternoon = utcMillis(2026, 9, 23, 14)
        val deepEvening = utcMillis(2026, 9, 23, 19)
        assertEquals(MapTheme.LIGHT, MapThemeResolver.resolve(MapThemeMode.AUTO, sofiaPoint(), brightAfternoon))
        assertEquals(MapTheme.DARK, MapThemeResolver.resolve(MapThemeMode.AUTO, sofiaPoint(), deepEvening))
    }
}
