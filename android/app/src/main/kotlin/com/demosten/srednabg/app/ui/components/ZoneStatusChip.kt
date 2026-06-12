// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.demosten.srednabg.R
import com.demosten.srednabg.app.ui.theme.SpeedAmberDeep
import com.demosten.srednabg.app.ui.theme.SpeedGreen
import com.demosten.srednabg.app.ui.theme.SpeedRed
import com.demosten.srednabg.app.ui.util.orDash
import com.demosten.srednabg.core.VehicleType
import com.demosten.srednabg.core.ZONE_COLOR_GREEN
import com.demosten.srednabg.core.ZONE_COLOR_RED
import com.demosten.srednabg.core.ZoneState
import com.demosten.srednabg.core.zoneStatusColor

/**
 * Exit verdict shown on the Exiting surfaces: did the final average exceed the
 * limit the engine judged against? Must use the vehicle-type-resolved limit —
 * the verdict would otherwise flip back to the car default for truck/bus.
 */
internal fun exitVerdictOverLimit(state: ZoneState.Exiting, vehicleType: VehicleType): Boolean {
    val finalAvg = state.finalAvgSpeed ?: return false
    return finalAvg > vehicleType.limit(state.zone.speedLimits)
}

/**
 * Driver-facing zone status card. Shared by the in-app [ZoneMapScreen] map
 * overlay and the system overlay window (`OverlayContent`). Renders nothing
 * when [state] is [ZoneState.Outside] — callers that want a compact idle
 * indicator (e.g. the floating overlay) use [ZoneStatusPill] for that case.
 */
@Composable
internal fun ZoneStatusChip(
    state: ZoneState,
    currentSpeedKmh: Double?,
    vehicleType: VehicleType,
    debugMaxSpeedOverride: Int?,
    modifier: Modifier = Modifier,
) {
    when (state) {
        is ZoneState.Outside -> Unit
        is ZoneState.InZone ->
            InZoneChip(state, currentSpeedKmh, vehicleType, debugMaxSpeedOverride, modifier)
        is ZoneState.Exiting -> ExitingChip(state, vehicleType, modifier)
    }
}

@Composable
private fun InZoneChip(
    state: ZoneState.InZone,
    currentSpeedKmh: Double?,
    vehicleType: VehicleType,
    debugMaxSpeedOverride: Int?,
    modifier: Modifier = Modifier,
) {
    // Vehicle-type-resolved limit — the engine's over-limit verdict uses it,
    // so the badge must show the same number, not the car default.
    val limit = vehicleType.limit(state.zone.speedLimits)
    // The chip's surface is the system theme's surfaceContainerHigh — light
    // in light theme, dark in dark theme — regardless of the map tile theme.
    // The core's zoneStatusColor returns the light-on-dark variants; swap to
    // the dark-on-light shades (SpeedRed/Amber/Green) when the chip is light.
    val statusColor = chipStatusColor(state, currentSpeedKmh)
    val statusLabel = stringResource(
        if (state.speedStatus.isOverLimit) R.string.status_over_limit else R.string.status_within_limit,
    )
    val nowText = stringResource(R.string.status_now_speed).format(currentSpeedKmh.orDash())
    val maxText = stringResource(R.string.max_for_remainder_format)
        .format(debugMaxSpeedOverride ?: state.speedStatus.maxSpeedForRemainder.toInt())
    val distanceKm = state.distanceRemaining / 1000.0
    val totalDist = state.zone.distanceM.toDouble().coerceAtLeast(1.0)
    val progress = ((totalDist - state.distanceRemaining) / totalDist).coerceIn(0.0, 1.0).toFloat()

    Surface(
        modifier = modifier,
        color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = 0.92f),
        contentColor = MaterialTheme.colorScheme.onSurface,
        shape = MaterialTheme.shapes.large,
        tonalElevation = 4.dp,
        shadowElevation = 6.dp,
        border = BorderStroke(1.5.dp, statusColor.copy(alpha = 0.65f)),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(statusColor.copy(alpha = 0.15f))
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Average + Now. End-aligned so the block hugs the centre limit
            // badge by the same gap the right column's full-width progress bar
            // does — keeps the badge visually equidistant from both sides.
            Column(
                modifier = Modifier.weight(1f),
                horizontalAlignment = Alignment.End,
            ) {
                // Big average speed with the unit baseline-aligned beside it
                // ("108 km/h"), so the unit sits on the number's bottom line.
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(
                        text = state.avgSpeed.orDash(),
                        color = statusColor,
                        fontWeight = FontWeight.Bold,
                        fontSize = 32.sp,
                        modifier = Modifier.alignByBaseline(),
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = stringResource(R.string.current_speed_label),
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.alignByBaseline(),
                    )
                }
                Text(
                    text = nowText,
                    style = MaterialTheme.typography.labelSmall,
                )
            }

            Spacer(modifier = Modifier.width(16.dp))

            // Speed limit badge
            Surface(
                modifier = Modifier.size(48.dp),
                shape = CircleShape,
                color = Color.White,
                border = BorderStroke(3.dp, Color(ZONE_COLOR_RED)),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        text = "$limit",
                        color = Color.Black,
                        fontWeight = FontWeight.Bold,
                        fontSize = 18.sp,
                    )
                }
            }

            Spacer(modifier = Modifier.width(16.dp))

            // Distance + progress + status + max
            Column(
                modifier = Modifier.weight(1f),
            ) {
                Text(
                    text = "%.1f km".format(distanceKm),
                    style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(modifier = Modifier.height(2.dp))
                LinearProgressIndicator(
                    progress = { progress },
                    color = statusColor,
                    trackColor = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(4.dp),
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = statusLabel,
                    color = statusColor,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.labelMedium,
                )
                Text(
                    text = maxText,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}

@Composable
private fun ExitingChip(
    state: ZoneState.Exiting,
    vehicleType: VehicleType,
    modifier: Modifier = Modifier,
) {
    val finalAvg = state.finalAvgSpeed
    val overLimit = exitVerdictOverLimit(state, vehicleType)
    val isLightChip = !isSystemInDarkTheme()
    val color = when {
        overLimit && isLightChip -> SpeedRed
        overLimit -> Color(ZONE_COLOR_RED)
        isLightChip -> SpeedGreen
        else -> Color(ZONE_COLOR_GREEN)
    }
    Surface(
        modifier = modifier,
        color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = 0.92f),
        contentColor = MaterialTheme.colorScheme.onSurface,
        shape = MaterialTheme.shapes.large,
        tonalElevation = 4.dp,
        shadowElevation = 6.dp,
        border = BorderStroke(1.5.dp, color.copy(alpha = 0.65f)),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(color.copy(alpha = 0.15f))
                .padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(R.string.zone_complete),
                style = MaterialTheme.typography.labelLarge,
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = stringResource(R.string.final_avg_speed).format(finalAvg.orDash()),
                color = color,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium,
            )
        }
    }
}

/**
 * Compact idle indicator shown by the floating system overlay while the driver
 * is between zones ([ZoneState.Outside]). Just the live speed in a small pill so
 * the overlay stays unobtrusive over Waze/Maps, then expands to [ZoneStatusChip]
 * on zone entry.
 */
@Composable
internal fun ZoneStatusPill(
    currentSpeedKmh: Double?,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = 0.92f),
        contentColor = MaterialTheme.colorScheme.onSurface,
        shape = MaterialTheme.shapes.large,
        tonalElevation = 4.dp,
        shadowElevation = 6.dp,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.4f)),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Image(
                painter = painterResource(R.drawable.ic_logo_mark),
                contentDescription = null,
                modifier = Modifier.size(22.dp),
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = currentSpeedKmh.orDash(),
                fontWeight = FontWeight.Bold,
                fontSize = 22.sp,
            )
            Spacer(modifier = Modifier.width(4.dp))
            Text(
                text = stringResource(R.string.current_speed_label),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun chipStatusColor(state: ZoneState.InZone, currentSpeedKmh: Double?): Color {
    // Amber tier is deliberately car-relative (matches core zoneStatusColor and
    // the iOS surfaces); red comes from the engine's vehicle-aware isOverLimit.
    val limit = state.zone.speedLimits.car
    return if (isSystemInDarkTheme()) {
        Color(zoneStatusColor(state, currentSpeedKmh))
    } else {
        when {
            state.speedStatus.isOverLimit -> SpeedRed
            currentSpeedKmh != null && currentSpeedKmh > limit -> SpeedAmberDeep
            else -> SpeedGreen
        }
    }
}
