// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import com.demosten.srednabg.app.data.local.toCoreZone
import com.demosten.srednabg.app.data.local.toEntity
import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import com.google.gson.Gson
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class ZoneEntityMapperTest {

    private val gson = Gson()

    private val sampleZone = Zone(
        id = "trakiya-01-west",
        road = "АМ Тракия",
        roadLatin = "Trakiya",
        direction = "west",
        description = "Ихтиман – Вакарел",
        start = ZoneEndpoint(
            lat = 42.427,
            lng = 23.855,
            kmMarker = "24+288",
            settlement = "Ихтиман",
            settlementLatin = "Ihtiman",
        ),
        end = ZoneEndpoint(
            lat = 42.550,
            lng = 23.703,
            kmMarker = "43+448",
            settlement = "Вакарел",
            settlementLatin = "Vakarel",
        ),
        distanceM = 19160,
        speedLimits = SpeedLimits(car = 140, truck = 90, bus = 100, motorcycle = 140),
        centerline = listOf(
            listOf(42.427, 23.855),
            listOf(42.480, 23.800),
            listOf(42.550, 23.703),
        ),
        source = "tolltracker",
        lastVerified = "2026-04-12",
    )

    @Test
    fun `roundtrip conversion preserves all fields`() {
        val entity = sampleZone.toEntity(gson)
        val restored = entity.toCoreZone(gson)

        assertEquals(sampleZone.id, restored.id)
        assertEquals(sampleZone.road, restored.road)
        assertEquals(sampleZone.roadLatin, restored.roadLatin)
        assertEquals(sampleZone.direction, restored.direction)
        assertEquals(sampleZone.description, restored.description)
        assertEquals(sampleZone.start, restored.start)
        assertEquals(sampleZone.end, restored.end)
        assertEquals(sampleZone.distanceM, restored.distanceM)
        assertEquals(sampleZone.speedLimits, restored.speedLimits)
        assertEquals(sampleZone.centerline, restored.centerline)
        assertEquals(sampleZone.source, restored.source)
        assertEquals(sampleZone.lastVerified, restored.lastVerified)
    }

    @Test
    fun `centerline JSON serialization produces valid JSON`() {
        val entity = sampleZone.toEntity(gson)
        val parsed: List<List<Double>> = gson.fromJson(
            entity.centerlineJson,
            object : com.google.gson.reflect.TypeToken<List<List<Double>>>() {}.type,
        )
        assertEquals(3, parsed.size)
        assertEquals(42.427, parsed[0][0])
        assertEquals(23.855, parsed[0][1])
    }

    @Test
    fun `nullable fields handled correctly`() {
        val zoneNoOptionals = sampleZone.copy(
            roadLatin = null,
            speedLimits = SpeedLimits(car = 90, truck = 80, bus = 80, motorcycle = null),
            start = sampleZone.start.copy(kmMarker = null, settlementLatin = null),
            end = sampleZone.end.copy(kmMarker = null, settlementLatin = null),
        )

        val entity = zoneNoOptionals.toEntity(gson)
        val restored = entity.toCoreZone(gson)

        assertNull(restored.roadLatin)
        assertNull(restored.speedLimits.motorcycle)
        assertNull(restored.start.kmMarker)
        assertNull(restored.start.settlementLatin)
    }

    @Test
    fun `entity fields map to correct columns`() {
        val entity = sampleZone.toEntity(gson)

        assertEquals("trakiya-01-west", entity.id)
        assertEquals(42.427, entity.startLat)
        assertEquals(23.855, entity.startLng)
        assertEquals(42.550, entity.endLat)
        assertEquals(23.703, entity.endLng)
        assertEquals(140, entity.speedLimitCar)
        assertEquals(90, entity.speedLimitTruck)
        assertEquals(100, entity.speedLimitBus)
        assertEquals(140, entity.speedLimitMotorcycle)
    }
}
