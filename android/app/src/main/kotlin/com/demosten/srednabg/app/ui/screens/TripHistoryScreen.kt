// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.screens

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.demosten.srednabg.R
import com.demosten.srednabg.app.ui.components.HistoryItemCard
import com.demosten.srednabg.app.ui.util.formatHistoryDay
import com.demosten.srednabg.app.ui.viewmodel.HistoryViewModel

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun TripHistoryScreen(
    onItemClick: (String) -> Unit,
    viewModel: HistoryViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    Scaffold { paddingValues ->
        if (uiState.groups.isEmpty()) {
            HistoryEmptyState(
                recordingDisabled = uiState.recordingDisabled,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
            )
            return@Scaffold
        }

        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item {
                Text(
                    text = stringResource(R.string.nav_history),
                    style = MaterialTheme.typography.headlineMedium,
                    modifier = Modifier.padding(bottom = 8.dp),
                )
            }
            uiState.groups.forEach { group ->
                stickyHeader(key = group.epochDay) {
                    Text(
                        text = formatHistoryDay(group.headerTimeMs),
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(MaterialTheme.colorScheme.surface)
                            .padding(vertical = 6.dp),
                    )
                }
                items(group.items, key = { it.id }) { item ->
                    HistoryItemCard(item = item, onClick = { onItemClick(item.id) })
                }
            }
        }
    }
}

@Composable
private fun HistoryEmptyState(
    recordingDisabled: Boolean,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(32.dp),
        ) {
            Text(
                text = stringResource(
                    if (recordingDisabled) R.string.history_disabled_title else R.string.history_empty_title,
                ),
                style = MaterialTheme.typography.titleMedium,
                textAlign = TextAlign.Center,
            )
            Text(
                text = stringResource(
                    if (recordingDisabled) R.string.history_disabled_body else R.string.history_empty_body,
                ),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
    }
}
