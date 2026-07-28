// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

const val ZONE_COLOR_GREEN: Int = 0xFF66BB6A.toInt()
const val ZONE_COLOR_YELLOW: Int = 0xFFFDD835.toInt()
const val ZONE_COLOR_RED: Int = 0xFFEF5350.toInt()

/**
 * The colour of "no verdict" — used for [ZoneState.Unmeasured], where we know the
 * driver is inside an average-speed zone but never saw the entry. Green / amber /
 * red *is* the verdict, so rendering any of them there would claim knowledge we
 * do not have.
 */
const val ZONE_COLOR_NEUTRAL: Int = 0xFF9E9E9E.toInt()

/**
 * Status traffic light for the in-zone HUD:
 * - **red** ([ZONE_COLOR_RED]) when the running average is already over the limit;
 * - **amber** ([ZONE_COLOR_YELLOW]) when the current instantaneous speed exceeds
 *   the **car** limit (recoverable — the average is still fine, ease off);
 * - **green** ([ZONE_COLOR_GREEN]) otherwise.
 *
 * The amber tier is deliberately keyed off `zone.speedLimits.car`, **not** the
 * vehicle-type-resolved limit, so the colour matches byte-for-byte across the
 * SwiftUI / UIKit / Compose surfaces (see ISSUE-002 — the iOS port documents the
 * same choice). Do **not** "fix" this to the per-vehicle limit without changing
 * both platforms together, or the traffic-light colour will diverge. Pass the
 * vehicle-aware limit upstream if per-vehicle colouring is ever wanted.
 */
fun zoneStatusColor(state: ZoneState.InZone, currentSpeedKmh: Double?): Int {
    return when {
        state.speedStatus.isOverLimit -> ZONE_COLOR_RED
        currentSpeedKmh != null && currentSpeedKmh > state.zone.speedLimits.car -> ZONE_COLOR_YELLOW
        else -> ZONE_COLOR_GREEN
    }
}
