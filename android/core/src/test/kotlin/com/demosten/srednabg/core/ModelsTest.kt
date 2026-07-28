// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class ModelsTest {

    @Test
    fun `zone creation with all fields`() {
        val zone = TRAKIYA_T10
        assertEquals("trakiya-01-west", zone.id)
        assertEquals("АМ Тракия", zone.road)
        assertEquals("west", zone.direction)
        assertEquals(19160, zone.distanceM)
        assertEquals(140, zone.speedLimits.car)
        assertEquals(6, zone.centerline.size)
    }

    @Test
    fun `zone state outside is singleton`() {
        val a = ZoneState.Outside
        val b = ZoneState.Outside
        assertEquals(a, b)
    }

    @Test
    fun `zone state in zone holds data`() {
        val status = SpeedStatus(
            avgSpeed = 130.0,
            maxSpeedForRemainder = 150.0,
            distanceRemaining = 10000.0,
            timeRemaining = 200.0,
            isOverLimit = false,
        )
        val state = ZoneState.InZone(
            zone = TRAKIYA_T10,
            entryTime = EPOCH_BASE,
            distanceTraveled = 9160.0,
            speedStatus = status,
            distanceRemaining = 10000.0,
        )
        assertEquals(TRAKIYA_T10, state.zone)
        // avgSpeed is a derived alias of speedStatus.avgSpeed.
        assertEquals(130.0, state.avgSpeed)
    }

    @Test
    fun `zone state sealed class pattern matching`() {
        val states: List<ZoneState> = listOf(
            ZoneState.Outside,
            ZoneState.InZone(TRAKIYA_T10, EPOCH_BASE, 0.0,
                SpeedStatus(0.0, 140.0, 19160.0, 492.0, false), 19160.0),
            ZoneState.Unmeasured(TRAKIYA_T10, 8000.0),
            ZoneState.Exiting(TRAKIYA_T10, 135.0),
        )

        val names = states.map { state ->
            when (state) {
                is ZoneState.Outside -> "outside"
                is ZoneState.InZone -> "inzone"
                is ZoneState.Unmeasured -> "unmeasured"
                is ZoneState.Exiting -> "exiting"
            }
        }
        assertEquals(listOf("outside", "inzone", "unmeasured", "exiting"), names)
    }

    @Test
    fun `gps point construction`() {
        val point = GpsPoint(lat = 42.5, lng = 23.8, speed = 130.0, timestamp = EPOCH_BASE, bearing = 270.0)
        assertEquals(42.5, point.lat)
        assertEquals(130.0, point.speed)
    }

    @Test
    fun `speed limits with optional motorcycle`() {
        val withMoto = SpeedLimits(car = 140, truck = 90, bus = 100, motorcycle = 140)
        assertEquals(140, withMoto.motorcycle)

        val withoutMoto = SpeedLimits(car = 90, truck = 80, bus = 80)
        assertTrue(withoutMoto.motorcycle == null)
    }
}
