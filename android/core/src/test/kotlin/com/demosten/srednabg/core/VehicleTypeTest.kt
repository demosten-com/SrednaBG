// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * Kept in lockstep with `ios/.../SrednaBGCoreTests/VehicleTypeTests.swift` —
 * the two cores must resolve identical limits and setting strings.
 */
class VehicleTypeTest {

    private val motorway = SpeedLimits(car = 140, truck = 90, bus = 100, motorcycle = 130)
    private val national = SpeedLimits(car = 90, truck = 80, bus = 80)

    @Test
    fun `each type picks its own limit`() {
        assertEquals(140, VehicleType.CAR.limit(motorway))
        assertEquals(90, VehicleType.TRUCK.limit(motorway))
        assertEquals(100, VehicleType.BUS.limit(motorway))
        assertEquals(130, VehicleType.MOTORCYCLE.limit(motorway))
    }

    @Test
    fun `motorcycle falls back to car when unset`() {
        assertEquals(90, VehicleType.MOTORCYCLE.limit(national))
    }

    /**
     * [VehicleType.BUS] is the whole `BE,C1,C1E,D,D1,D1E,DE` licence class, so a
     * car towing a trailer and a 3.5–7.5 t truck resolve it too — that is why the
     * Settings row names the class, not just buses. Pins that it stays distinct
     * from the car limit, which is the value those drivers would otherwise get.
     */
    @Test
    fun `bus is the whole BE-C1-D licence class and differs from car`() {
        assertEquals(100, VehicleType.BUS.limit(motorway))
        assertEquals(80, VehicleType.BUS.limit(national))
        assertEquals(VehicleType.BUS.limit(motorway), motorway.bus)
    }

    @Test
    fun `fromSetting maps every persisted token`() {
        assertEquals(VehicleType.CAR, VehicleType.fromSetting("car"))
        assertEquals(VehicleType.TRUCK, VehicleType.fromSetting("truck"))
        assertEquals(VehicleType.BUS, VehicleType.fromSetting("bus"))
        assertEquals(VehicleType.MOTORCYCLE, VehicleType.fromSetting("motorcycle"))
    }

    @Test
    fun `fromSetting falls back to car for unknown tokens`() {
        assertEquals(VehicleType.CAR, VehicleType.fromSetting("bogus"))
        assertEquals(VehicleType.CAR, VehicleType.fromSetting(""))
        // The removed car-with-trailer type must not linger as a live token —
        // a stale setting value falls back to CAR like any other unknown.
        assertEquals(VehicleType.CAR, VehicleType.fromSetting("car_trailer"))
    }

    /**
     * The persisted tokens, spelled out. These are written to the vehicle-type
     * setting AND to `ZoneTraversalEntity.vehicleType`, and must equal the Swift
     * `VehicleType` raw values — `VehicleTypeTests.swift` asserts the same list.
     */
    @Test
    fun `every case has a setting token that round-trips`() {
        val tokens = mapOf(
            VehicleType.CAR to "car",
            VehicleType.TRUCK to "truck",
            VehicleType.BUS to "bus",
            VehicleType.MOTORCYCLE to "motorcycle",
        )
        assertEquals(VehicleType.entries.toSet(), tokens.keys)
        tokens.forEach { (type, token) ->
            assertEquals(token, type.setting)
            assertEquals(type, VehicleType.fromSetting(token))
        }
    }

    /**
     * The history recorder and the debug seeder persist [VehicleType.setting],
     * NOT `name.lowercase()`. Those agree for today's four single-word cases, so
     * this pins the rule while it is still free: iOS spells raw values in
     * camelCase, so any multi-word case added later would diverge silently.
     */
    @Test
    fun `setting tokens are single lowercase words that match the iOS raw values`() {
        for (type in VehicleType.entries) {
            assertEquals(type.name.lowercase(), type.setting)
            assertTrue(type.setting.none { it == '_' }, "${'$'}{type.setting} is multi-word")
        }
    }
}
