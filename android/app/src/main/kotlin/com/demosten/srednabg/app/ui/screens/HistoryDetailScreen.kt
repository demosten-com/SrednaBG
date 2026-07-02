// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.demosten.srednabg.R
import com.demosten.srednabg.app.ui.components.SpeedGraph
import com.demosten.srednabg.app.ui.components.historyVerdictColor
import com.demosten.srednabg.app.ui.util.directionLabel
import com.demosten.srednabg.app.ui.util.formatDuration
import com.demosten.srednabg.app.ui.util.formatHistoryDateTime
import com.demosten.srednabg.app.ui.util.orDash
import com.demosten.srednabg.app.ui.viewmodel.HistoryDetail
import com.demosten.srednabg.app.ui.viewmodel.HistoryDetailUiState
import com.demosten.srednabg.app.ui.viewmodel.HistoryViewModel
import com.demosten.srednabg.core.ZONE_COLOR_RED

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryDetailScreen(
    id: String,
    onBack: () -> Unit,
    viewModel: HistoryViewModel = hiltViewModel(),
) {
    LaunchedEffect(id) { viewModel.loadDetail(id) }
    val state by viewModel.detailState.collectAsStateWithLifecycle()
    val loaded = state as? HistoryDetailUiState.Loaded

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        loaded?.detail?.roadLatin
                            ?: loaded?.detail?.road
                            ?: stringResource(R.string.nav_history),
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = stringResource(R.string.action_back),
                        )
                    }
                },
            )
        },
    ) { paddingValues ->
        when (val s = state) {
            HistoryDetailUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
            }

            HistoryDetailUiState.NotFound -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = stringResource(R.string.history_not_found),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            is HistoryDetailUiState.Loaded -> {
                val d = s.detail
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    val verdictColor = historyVerdictColor(d.isOverLimit)
                    StatsCard(d, verdictColor)
                    GraphCard(d, verdictColor)
                }
            }
        }
    }
}

@Composable
private fun StatsCard(d: HistoryDetail, verdictColor: Color) {
    VerdictCard(verdictColor) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            directionLabel(d.direction)?.let { direction ->
                StatRow(stringResource(R.string.history_direction), direction)
            }
            StatRow(stringResource(R.string.history_entered), formatHistoryDateTime(d.entryTimeMs))
            StatRow(stringResource(R.string.history_exited), formatHistoryDateTime(d.exitTimeMs))
            StatRow(stringResource(R.string.history_duration), formatDuration(d.exitTimeMs - d.entryTimeMs))
            StatRow(
                label = stringResource(R.string.history_your_average),
                value = stringResource(R.string.history_kmh_value, d.avgSpeedKmh.orDash()),
                valueColor = verdictColor,
                emphasize = true,
            )
            StatRow(
                stringResource(R.string.history_top_speed),
                stringResource(R.string.history_kmh_value, d.sustainedMaxKmh.orDash()),
            )
            StatRow(
                stringResource(R.string.history_lowest_speed),
                stringResource(R.string.history_kmh_value, d.sustainedMinKmh.orDash()),
            )
            StatRow(
                label = stringResource(
                    if (d.isOverLimit) R.string.status_over_limit else R.string.status_within_limit,
                ),
                value = stringResource(R.string.history_kmh_value, d.limitKmh.toString()),
                valueColor = verdictColor,
            )
        }
    }
}

@Composable
private fun StatRow(
    label: String,
    value: String,
    valueColor: Color = MaterialTheme.colorScheme.onSurface,
    emphasize: Boolean = false,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = value,
            style = if (emphasize) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyLarge,
            color = valueColor,
            fontWeight = if (emphasize) FontWeight.Bold else FontWeight.Medium,
        )
    }
}

@Composable
private fun GraphCard(d: HistoryDetail, verdictColor: Color) {
    VerdictCard(verdictColor) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.history_graph_title),
                style = MaterialTheme.typography.titleSmall,
            )
            SpeedGraph(
                samples = d.samples,
                avgSpeedKmh = d.avgSpeedKmh,
                limitKmh = d.limitKmh,
                lineColor = MaterialTheme.colorScheme.primary,
                averageColor = MaterialTheme.colorScheme.onSurfaceVariant,
                limitColor = Color(ZONE_COLOR_RED),
                gridColor = MaterialTheme.colorScheme.outlineVariant,
                axisLabelStyle = MaterialTheme.typography.labelSmall.copy(
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                ),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                LegendDot(MaterialTheme.colorScheme.primary, stringResource(R.string.history_legend_speed))
                LegendDot(MaterialTheme.colorScheme.onSurfaceVariant, stringResource(R.string.history_legend_average))
                LegendDot(Color(ZONE_COLOR_RED), stringResource(R.string.history_legend_limit))
            }
        }
    }
}

/**
 * Detail-screen data group. Base surface matches the in-zone/exit chip and the
 * history list row; the verdict tint (green within / red over) composites over
 * it at the same 0.15 alpha, so every group reads the outcome consistently in
 * both themes instead of the default surfaceContainerLow (faint green in light).
 */
@Composable
private fun VerdictCard(verdictColor: Color, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
        ),
    ) {
        Box(modifier = Modifier.background(verdictColor.copy(alpha = 0.15f))) {
            content()
        }
    }
}

@Composable
private fun LegendDot(color: Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Surface(modifier = Modifier.size(10.dp), shape = CircleShape, color = color) {}
        Spacer(modifier = Modifier.size(4.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
