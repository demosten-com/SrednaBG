// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

const val ZONE_COLOR_GREEN: Int = 0xFF66BB6A.toInt()
const val ZONE_COLOR_YELLOW: Int = 0xFFFDD835.toInt()
const val ZONE_COLOR_RED: Int = 0xFFEF5350.toInt()

fun zoneStatusColor(state: ZoneState.InZone, currentSpeedKmh: Double?): Int {
    return when {
        state.speedStatus.isOverLimit -> ZONE_COLOR_RED
        currentSpeedKmh != null && currentSpeedKmh > state.zone.speedLimits.car -> ZONE_COLOR_YELLOW
        else -> ZONE_COLOR_GREEN
    }
}
