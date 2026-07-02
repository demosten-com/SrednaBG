// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.demosten.srednabg.R
import com.demosten.srednabg.app.ui.theme.SpeedGreen
import com.demosten.srednabg.app.ui.theme.SpeedRed
import com.demosten.srednabg.app.ui.util.directionLabel
import com.demosten.srednabg.app.ui.util.formatHistoryTime
import com.demosten.srednabg.app.ui.util.orDash
import com.demosten.srednabg.app.ui.viewmodel.HistoryListItem
import com.demosten.srednabg.core.ZONE_COLOR_GREEN
import com.demosten.srednabg.core.ZONE_COLOR_RED

/**
 * A single History row, echoing the in-zone chip's visual language: the road,
 * the round posted-limit badge, and the driver's average tinted green (within)
 * or red (over) — the same verdict colours used on the exit chip.
 */
@Composable
internal fun HistoryItemCard(
    item: HistoryListItem,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val color = historyVerdictColor(item.isOverLimit)
    Card(
        onClick = onClick,
        modifier = modifier.fillMaxWidth(),
        // Base surface matches the in-zone/exit chip; the verdict tint composites
        // over it (below) so the row reads green/red consistently in both themes
        // instead of the default surfaceContainerLow (faint green in light,
        // neutral grey in dark) that conveyed no verdict.
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
        ),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(color.copy(alpha = 0.15f))
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.roadLatin ?: item.road,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                val direction = directionLabel(item.direction)
                val subtitle = formatHistoryTime(item.exitTimeMs).let { time ->
                    if (direction != null) "$time · $direction" else time
                }
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(modifier = Modifier.width(12.dp))

            // Posted average-speed limit badge (same as the in-zone chip).
            Surface(
                modifier = Modifier.size(44.dp),
                shape = CircleShape,
                color = Color.White,
                border = BorderStroke(3.dp, Color(ZONE_COLOR_RED)),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        text = "${item.limitKmh}",
                        color = Color.Black,
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                    )
                }
            }

            Spacer(modifier = Modifier.width(16.dp))

            // Driver's average, tinted by the within/over verdict.
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = item.avgSpeedKmh.orDash(),
                    color = color,
                    fontWeight = FontWeight.Bold,
                    fontSize = 26.sp,
                )
                Text(
                    text = stringResource(R.string.avg_speed_label),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/**
 * Within/over verdict tint, matching the exit chip: the dark-on-light
 * SpeedGreen/SpeedRed in light theme, the light-on-dark packed colours in dark.
 */
@Composable
internal fun historyVerdictColor(isOverLimit: Boolean): Color {
    val light = !isSystemInDarkTheme()
    return when {
        isOverLimit && light -> SpeedRed
        isOverLimit -> Color(ZONE_COLOR_RED)
        light -> SpeedGreen
        else -> Color(ZONE_COLOR_GREEN)
    }
}
