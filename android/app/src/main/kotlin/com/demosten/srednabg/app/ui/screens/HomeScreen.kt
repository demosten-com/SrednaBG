// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.demosten.srednabg.R
import com.demosten.srednabg.app.ui.theme.SpeedAmber
import com.demosten.srednabg.app.ui.theme.SpeedGreen
import com.demosten.srednabg.app.ui.theme.SpeedRed
import com.demosten.srednabg.app.ui.util.orDash
import com.demosten.srednabg.app.ui.viewmodel.HomeViewModel
import com.demosten.srednabg.core.ZoneState

@Composable
fun HomeScreen(viewModel: HomeViewModel = hiltViewModel()) {
    val zoneState by viewModel.zoneState.collectAsStateWithLifecycle()
    val isTracking by viewModel.isTracking.collectAsStateWithLifecycle()
    val zoneCount by viewModel.zoneCount.collectAsStateWithLifecycle()
    val currentSpeedKmh by viewModel.currentSpeedKmh.collectAsStateWithLifecycle()

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(16.dp)
                .fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            StateContent(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                zoneState = zoneState,
                isTracking = isTracking,
                zoneCount = zoneCount,
                currentSpeedKmh = currentSpeedKmh,
            )

            val buttonLabel = if (isTracking) {
                stringResource(R.string.stop_tracking)
            } else {
                stringResource(R.string.start_tracking)
            }
            Button(
                onClick = {
                    if (isTracking) viewModel.stopTracking() else viewModel.startTracking()
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(72.dp),
                colors = if (isTracking) {
                    ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer,
                        contentColor = MaterialTheme.colorScheme.onErrorContainer,
                    )
                } else {
                    ButtonDefaults.buttonColors()
                },
            ) {
                Icon(
                    imageVector = if (isTracking) Icons.Default.Stop else Icons.Default.PlayArrow,
                    contentDescription = null,
                )
                Spacer(modifier = Modifier.width(12.dp))
                Text(
                    text = buttonLabel,
                    style = MaterialTheme.typography.titleMedium,
                )
            }
        }
    }
}

@Composable
private fun StateContent(
    modifier: Modifier,
    zoneState: ZoneState,
    isTracking: Boolean,
    zoneCount: Int,
    currentSpeedKmh: Double?,
) {
    when {
        !isTracking -> NotTrackingCard(modifier)
        zoneState is ZoneState.InZone -> InZoneCard(modifier, zoneState, currentSpeedKmh)
        zoneState is ZoneState.Exiting -> ExitingCard(modifier, zoneState, currentSpeedKmh)
        else -> OutsideCard(modifier, currentSpeedKmh, zoneCount)
    }
}

@Composable
private fun NotTrackingCard(modifier: Modifier) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Box(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = stringResource(R.string.status_not_tracking),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = stringResource(R.string.tap_to_start_hint),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun OutsideCard(modifier: Modifier, currentSpeedKmh: Double?, zoneCount: Int) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f),
        ),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(R.string.status_tracking_outside),
                style = MaterialTheme.typography.titleMedium,
            )
            Box(
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = currentSpeedKmh.orDash(),
                        fontSize = 128.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = stringResource(R.string.current_speed_label),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Text(
                text = stringResource(R.string.zones_loaded, zoneCount),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun InZoneCard(modifier: Modifier, state: ZoneState.InZone, currentSpeedKmh: Double?) {
    val statusColor = when {
        state.speedStatus.isOverLimit -> SpeedRed
        currentSpeedKmh != null && currentSpeedKmh > state.zone.speedLimits.car -> SpeedAmber
        else -> SpeedGreen
    }
    val statusText = if (state.speedStatus.isOverLimit) {
        stringResource(R.string.status_over_limit)
    } else {
        stringResource(R.string.status_within_limit)
    }
    val semanticDescription = stringResource(
        R.string.accessibility_in_zone,
        state.avgSpeed.orDash(),
        state.zone.speedLimits.car,
        statusText,
    )

    Card(
        modifier = modifier.semantics { contentDescription = semanticDescription },
        colors = CardDefaults.cardColors(containerColor = statusColor.copy(alpha = 0.15f)),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
        ) {
            Text(
                text = stringResource(R.string.status_in_zone, state.zone.road),
                style = MaterialTheme.typography.titleMedium,
            )

            Box(
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = state.avgSpeed.orDash(),
                        fontSize = 128.sp,
                        fontWeight = FontWeight.Bold,
                        color = statusColor,
                    )
                    Text(
                        text = stringResource(R.string.avg_speed_label),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = stringResource(R.string.status_now_speed, currentSpeedKmh.orDash()),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                InfoItem(
                    label = stringResource(R.string.speed_limit),
                    value = "${state.zone.speedLimits.car}",
                )
                InfoItem(
                    label = stringResource(R.string.max_for_remainder),
                    value = "${state.speedStatus.maxSpeedForRemainder.toInt()}",
                )
                InfoItem(
                    label = stringResource(R.string.remaining),
                    value = "%.1f km".format(state.distanceRemaining / 1000),
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = statusText,
                style = MaterialTheme.typography.titleMedium,
                color = statusColor,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun ExitingCard(modifier: Modifier, state: ZoneState.Exiting, currentSpeedKmh: Double?) {
    val finalAvg = state.finalAvgSpeed
    val color = if (finalAvg != null && finalAvg > state.zone.speedLimits.car) SpeedRed else SpeedGreen
    val semanticDescription = stringResource(
        R.string.accessibility_exiting,
        state.finalAvgSpeed.orDash(),
        state.zone.road,
    )

    Card(
        modifier = modifier.semantics { contentDescription = semanticDescription },
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.15f)),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(R.string.status_exiting, state.zone.road),
                style = MaterialTheme.typography.titleMedium,
            )
            Box(
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = stringResource(R.string.final_avg_speed, state.finalAvgSpeed.orDash()),
                        style = MaterialTheme.typography.headlineLarge,
                        color = color,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
            Text(
                text = stringResource(R.string.status_now_speed, currentSpeedKmh.orDash()),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun InfoItem(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(text = value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(text = label, style = MaterialTheme.typography.bodySmall)
    }
}
