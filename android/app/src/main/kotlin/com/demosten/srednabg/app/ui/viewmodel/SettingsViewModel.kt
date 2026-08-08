// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.SyncResult
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.data.ZoneSyncScheduler
import com.demosten.srednabg.core.MapThemeMode
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val settingsRepository: SettingsRepository,
    private val zoneRepository: ZoneRepository,
    private val zoneSyncScheduler: ZoneSyncScheduler,
) : ViewModel() {

    val voiceEnabled: StateFlow<Boolean> = settingsRepository.voiceEnabled
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), true)

    val periodicVoiceUpdates: StateFlow<Boolean> = settingsRepository.periodicVoiceUpdates
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(5000),
            SettingsRepository.DEFAULT_PERIODIC_VOICE_UPDATES,
        )

    val announceOnlyWhenOver: StateFlow<Boolean> = settingsRepository.announceOnlyWhenOver
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(5000),
            SettingsRepository.DEFAULT_ANNOUNCE_ONLY_WHEN_OVER,
        )

    val appLanguage: StateFlow<String> = settingsRepository.appLanguage
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), SettingsRepository.DEFAULT_APP_LANGUAGE)

    val vehicleType: StateFlow<String> = settingsRepository.vehicleType
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), SettingsRepository.DEFAULT_VEHICLE_TYPE)

    val mapThemeMode: StateFlow<MapThemeMode> = settingsRepository.mapThemeMode
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), SettingsRepository.DEFAULT_MAP_THEME_MODE)

    val autoStopHours: StateFlow<Int> = settingsRepository.autoStopHours
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), SettingsRepository.DEFAULT_AUTO_STOP_HOURS)

    val historyRetention: StateFlow<String> = settingsRepository.historyRetention
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(5000),
            SettingsRepository.DEFAULT_HISTORY_RETENTION,
        )

    val zoneSyncEnabled: StateFlow<Boolean> = settingsRepository.zoneSyncEnabled
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(5000),
            SettingsRepository.DEFAULT_ZONE_SYNC_ENABLED,
        )

    val overlayEnabled: StateFlow<Boolean> = settingsRepository.overlayEnabled
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(5000),
            SettingsRepository.DEFAULT_OVERLAY_ENABLED,
        )

    val zoneDataVersion: StateFlow<String> = settingsRepository.cachedZoneVersion
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), "")

    val zoneDataHash: StateFlow<String> = settingsRepository.cachedZoneHash
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), "")

    val zoneCount: StateFlow<Int> = zoneRepository.zones
        .map { it.size }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 0)

    private val _isSyncing = MutableStateFlow(false)
    val isSyncing: StateFlow<Boolean> = _isSyncing.asStateFlow()

    private val _syncEvents = Channel<SyncResult>(Channel.BUFFERED)
    val syncEvents = _syncEvents.receiveAsFlow()

    fun setVoiceEnabled(value: Boolean) {
        viewModelScope.launch { settingsRepository.setVoiceEnabled(value) }
    }

    fun setPeriodicVoiceUpdates(value: Boolean) {
        viewModelScope.launch { settingsRepository.setPeriodicVoiceUpdates(value) }
    }

    fun setAnnounceOnlyWhenOver(value: Boolean) {
        viewModelScope.launch { settingsRepository.setAnnounceOnlyWhenOver(value) }
    }

    fun setAppLanguage(value: String) {
        viewModelScope.launch { settingsRepository.setAppLanguage(value) }
    }

    fun setVehicleType(value: String) {
        viewModelScope.launch { settingsRepository.setVehicleType(value) }
    }

    fun setMapThemeMode(value: MapThemeMode) {
        viewModelScope.launch { settingsRepository.setMapThemeMode(value) }
    }

    fun setAutoStopHours(value: Int) {
        viewModelScope.launch { settingsRepository.setAutoStopHours(value) }
    }

    fun setHistoryRetention(value: String) {
        viewModelScope.launch { settingsRepository.setHistoryRetention(value) }
    }

    fun setZoneSyncEnabled(value: Boolean) {
        viewModelScope.launch {
            settingsRepository.setZoneSyncEnabled(value)
            if (value) zoneSyncScheduler.enable() else zoneSyncScheduler.disable()
        }
    }

    fun setOverlayEnabled(value: Boolean) {
        viewModelScope.launch { settingsRepository.setOverlayEnabled(value) }
    }

    fun syncNow() {
        if (_isSyncing.value) return
        viewModelScope.launch {
            _isSyncing.value = true
            val result = zoneRepository.syncFromServer()
            _syncEvents.trySend(result)
            _isSyncing.value = false
        }
    }
}
