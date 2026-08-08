// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

/**
 * Driver-selected vehicle type, used to pick the speed limit that applies in a
 * zone. Mirrors the Swift `VehicleType` in `ios/.../SrednaBGCore/VehicleType.swift`.
 * Motorcycle falls back to the car limit when a zone has no explicit value.
 *
 * These map onto BG TOLL's three licence-category classes, NOT onto vehicle
 * shapes — see the note on [SpeedLimits]. [BUS] is the whole
 * `BE,C1,C1E,D,D1,D1E,DE` class, so it is also what a car towing a trailer or a
 * 3.5–7.5 t truck selects; the Settings row is labelled for the class rather
 * than for buses alone. There is deliberately no separate car-with-trailer case:
 * it would be a second enum value resolving an identical limit.
 */
enum class VehicleType(
    /**
     * The persisted token for this type — the value stored in the vehicle-type
     * setting and in `ZoneTraversalEntity.vehicleType`. Equal to the Swift
     * `VehicleType` raw value, so both platforms write the same history rows.
     *
     * Declared explicitly rather than derived from [name]: iOS spells its raw
     * values in camelCase, so any multi-word case added here would silently
     * diverge (`FOO_BAR.name.lowercase()` = `foo_bar` vs iOS's `fooBar`).
     */
    val setting: String,
) {
    CAR("car"),
    TRUCK("truck"),
    BUS("bus"),
    MOTORCYCLE("motorcycle"),
    ;

    fun limit(limits: SpeedLimits): Int = when (this) {
        CAR -> limits.car
        TRUCK -> limits.truck
        BUS -> limits.bus
        MOTORCYCLE -> limits.motorcycle ?: limits.car
    }

    companion object {
        /**
         * Map a `SettingsRepository.vehicleType` string to a [VehicleType].
         * Anything unrecognized (including the default `"car"`) maps to [CAR].
         *
         * The setting strings are shared with iOS, where they are the
         * `VehicleType` raw values — keep the two spellings identical.
         */
        fun fromSetting(setting: String): VehicleType =
            entries.firstOrNull { it.setting == setting } ?: CAR
    }
}
