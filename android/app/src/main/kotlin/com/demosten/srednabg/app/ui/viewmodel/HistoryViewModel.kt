// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.demosten.srednabg.app.data.HistoryRepository
import com.demosten.srednabg.app.data.MapHighlightStore
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.data.local.ZoneTraversalEntity
import com.demosten.srednabg.app.data.local.speedSamples
import com.demosten.srednabg.app.service.LocationTrackingService
import com.demosten.srednabg.app.ui.util.epochDay
import com.demosten.srednabg.core.SpeedSample
import com.google.gson.Gson
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

/** A single History row (samples not parsed — the detail screen loads those). */
data class HistoryListItem(
    val id: String,
    val road: String,
    val roadLatin: String?,
    val direction: String,
    val avgSpeedKmh: Double?,
    val limitKmh: Int,
    val isOverLimit: Boolean,
    val exitTimeMs: Long,
)

/** Rows sharing one local calendar day, rendered under a sticky header. */
data class HistoryDayGroup(
    val epochDay: Long,
    val headerTimeMs: Long,
    val items: List<HistoryListItem>,
)

/** Fully-hydrated single traversal for the detail screen (samples parsed). */
data class HistoryDetail(
    val id: String,
    val zoneId: String,
    val road: String,
    val roadLatin: String?,
    val direction: String,
    val entryTimeMs: Long,
    val exitTimeMs: Long,
    val avgSpeedKmh: Double?,
    val sustainedMinKmh: Double,
    val sustainedMaxKmh: Double,
    val limitKmh: Int,
    val isOverLimit: Boolean,
    val distanceM: Int,
    val samples: List<SpeedSample>,
)

@HiltViewModel
class HistoryViewModel @Inject constructor(
    private val historyRepository: HistoryRepository,
    settingsRepository: SettingsRepository,
    zoneRepository: ZoneRepository,
    private val mapHighlightStore: MapHighlightStore,
    private val gson: Gson,
) : ViewModel() {

    /** True while retention is "none" — the UI shows the disabled/empty prompt. */
    val recordingDisabled: StateFlow<Boolean> = settingsRepository.historyRetention
        .map { it == "none" }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)

    val days: StateFlow<List<HistoryDayGroup>> = historyRepository.observeAll()
        .map { entities -> entities.toDayGroups() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    /** Combined so the empty state can distinguish "no records" from "disabled". */
    val uiState: StateFlow<HistoryUiState> = combine(days, recordingDisabled) { groups, disabled ->
        HistoryUiState(groups = groups, recordingDisabled = disabled)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), HistoryUiState())

    private val _detailState = MutableStateFlow<HistoryDetailUiState>(HistoryDetailUiState.Loading)
    val detailState: StateFlow<HistoryDetailUiState> = _detailState.asStateFlow()

    /**
     * "Show on map" is available only when the detail is loaded, its zone still
     * exists in the current catalog (a sync can delete zones), and tracking is
     * off — live tracking and the history highlight must not drive the map at
     * the same time.
     */
    val canShowOnMap: StateFlow<Boolean> = combine(
        detailState,
        zoneRepository.zones,
        LocationTrackingService.isTracking,
    ) { state, zones, tracking ->
        val detail = (state as? HistoryDetailUiState.Loaded)?.detail
        detail != null && !tracking && zones.any { it.id == detail.zoneId }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)

    fun showOnMap() {
        val detail = (detailState.value as? HistoryDetailUiState.Loaded)?.detail ?: return
        mapHighlightStore.request(detail.zoneId, detail.isOverLimit)
    }

    fun loadDetail(id: String) {
        // Reset to Loading so the detail screen shows a spinner (not the "no
        // records" empty state) until the one-shot lookup resolves.
        _detailState.value = HistoryDetailUiState.Loading
        viewModelScope.launch {
            val detail = historyRepository.getById(id)?.toDetail(gson)
            _detailState.value =
                if (detail != null) HistoryDetailUiState.Loaded(detail) else HistoryDetailUiState.NotFound
        }
    }

    private fun List<ZoneTraversalEntity>.toDayGroups(): List<HistoryDayGroup> =
        // Already exitTimeMs DESC from the DAO, so groups and items stay
        // most-recent-first without re-sorting.
        groupBy { epochDay(it.exitTimeMs) }
            .map { (day, rows) ->
                HistoryDayGroup(
                    epochDay = day,
                    headerTimeMs = rows.first().exitTimeMs,
                    items = rows.map { it.toListItem() },
                )
            }
            .sortedByDescending { it.epochDay }

    private fun ZoneTraversalEntity.toListItem() = HistoryListItem(
        id = id,
        road = road,
        roadLatin = roadLatin,
        direction = direction,
        avgSpeedKmh = avgSpeedKmh,
        limitKmh = speedLimitKmh,
        isOverLimit = isOverLimit,
        exitTimeMs = exitTimeMs,
    )

    private fun ZoneTraversalEntity.toDetail(gson: Gson) = HistoryDetail(
        id = id,
        zoneId = zoneId,
        road = road,
        roadLatin = roadLatin,
        direction = direction,
        entryTimeMs = entryTimeMs,
        exitTimeMs = exitTimeMs,
        avgSpeedKmh = avgSpeedKmh,
        sustainedMinKmh = sustainedMinKmh,
        sustainedMaxKmh = sustainedMaxKmh,
        limitKmh = speedLimitKmh,
        isOverLimit = isOverLimit,
        distanceM = distanceM,
        samples = speedSamples(gson),
    )
}

data class HistoryUiState(
    val groups: List<HistoryDayGroup> = emptyList(),
    val recordingDisabled: Boolean = false,
)

/** Detail-screen state, distinguishing the in-flight load from a genuine miss. */
sealed interface HistoryDetailUiState {
    data object Loading : HistoryDetailUiState
    data object NotFound : HistoryDetailUiState
    data class Loaded(val detail: HistoryDetail) : HistoryDetailUiState
}
