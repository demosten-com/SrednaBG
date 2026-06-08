// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

/**
 * Driver-selected vehicle type, used to pick the speed limit that applies in a
 * zone. Mirrors the Swift `VehicleType` in `ios/.../SrednaBGCore/VehicleType.swift`.
 * Motorcycle falls back to the car limit when a zone has no explicit value.
 */
enum class VehicleType {
    CAR,
    TRUCK,
    BUS,
    MOTORCYCLE,
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
         */
        fun fromSetting(setting: String): VehicleType = when (setting) {
            "truck" -> TRUCK
            "bus" -> BUS
            "motorcycle" -> MOTORCYCLE
            else -> CAR
        }
    }
}
