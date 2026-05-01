// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.demosten.srednabg.app.data.MapRepository
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.service.LocationTrackingService
import com.demosten.srednabg.core.GpsPoint
import com.demosten.srednabg.core.MapTheme
import com.demosten.srednabg.core.MapThemeMode
import com.demosten.srednabg.core.MapThemeResolver
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneState
import com.demosten.srednabg.core.snapToZone
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ZoneMapViewModel @Inject constructor(
    private val zoneRepository: ZoneRepository,
    private val settingsRepository: SettingsRepository,
    private val mapRepository: MapRepository,
) : ViewModel() {

    fun styleUriFor(theme: MapTheme): String = mapRepository.localStyleUri(theme)

    val zones: StateFlow<List<Zone>> = zoneRepository.zones
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val currentPosition: StateFlow<GpsPoint?> = LocationTrackingService.currentPosition

    val zoneState: StateFlow<ZoneState> = LocationTrackingService.zoneState

    val activeZoneId: StateFlow<String?> = LocationTrackingService.zoneState
        .map { state ->
            when (state) {
                is ZoneState.InZone -> state.zone.id
                is ZoneState.Exiting -> state.zone.id
                ZoneState.Outside -> null
            }
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    val displayPosition: StateFlow<GpsPoint?> =
        combine(LocationTrackingService.currentPosition, LocationTrackingService.zoneState) { pos, state ->
            snapToZone(pos, state)
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    val mapHeadingUp: StateFlow<Boolean> = settingsRepository.mapHeadingUp
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)

    /**
     * Effective map theme. Combines the user's mode (Auto/Light/Dark) with
     * the current GPS position and a 60s wall-clock ticker so the auto
     * day/night transition fires within a minute of crossing civil
     * twilight at the user's location. Symmetric ±0.5° hysteresis around
     * the boundary suppresses flicker for users parked right at the
     * twilight margin.
     */
    val mapTheme: StateFlow<MapTheme> = combine(
        settingsRepository.mapThemeMode,
        LocationTrackingService.currentPosition,
        clockTicker(intervalMs = THEME_TICK_MS),
    ) { mode, position, nowMs ->
        Triple(mode, position, nowMs)
    }
        .map(::resolveWithHysteresis)
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(5000),
            initialValue = MapThemeResolver.resolve(
                MapThemeMode.AUTO, position = null, nowMillisUtc = System.currentTimeMillis(),
            ),
        )

    private var lastTheme: MapTheme? = null

    private fun resolveWithHysteresis(input: Triple<MapThemeMode, GpsPoint?, Long>): MapTheme {
        val (mode, position, nowMs) = input
        if (mode != MapThemeMode.AUTO) {
            val theme = if (mode == MapThemeMode.LIGHT) MapTheme.LIGHT else MapTheme.DARK
            lastTheme = theme
            return theme
        }
        val lat = position?.lat ?: MapThemeResolver.FALLBACK_LAT_SOFIA
        val lng = position?.lng ?: MapThemeResolver.FALLBACK_LNG_SOFIA
        val altitudeDeg = MapThemeResolver.solarAltitudeDegrees(lat, lng, nowMs)
        val previous = lastTheme
        val boundary = MapThemeResolver.CIVIL_TWILIGHT_ALTITUDE_DEG
        val resolved = when (previous) {
            MapTheme.LIGHT -> if (altitudeDeg < boundary - HYSTERESIS_MARGIN_DEG) MapTheme.DARK else MapTheme.LIGHT
            MapTheme.DARK -> if (altitudeDeg > boundary + HYSTERESIS_MARGIN_DEG) MapTheme.LIGHT else MapTheme.DARK
            null -> if (altitudeDeg > boundary) MapTheme.LIGHT else MapTheme.DARK
        }
        lastTheme = resolved
        return resolved
    }

    private val _isSyncing = MutableStateFlow(false)
    val isSyncing: StateFlow<Boolean> = _isSyncing.asStateFlow()

    // Survives navigation away from / back to the Map tab so the user's zoom +
    // pan don't get clobbered by the on-entry zone-fit. Lives in the VM (not
    // DataStore) — process death legitimately resets to the default view.
    private val _cameraSnapshot = MutableStateFlow<MapCameraSnapshot?>(null)
    val cameraSnapshot: StateFlow<MapCameraSnapshot?> = _cameraSnapshot.asStateFlow()

    fun saveCameraSnapshot(snapshot: MapCameraSnapshot) {
        _cameraSnapshot.value = snapshot
    }

    fun retrySync() {
        if (_isSyncing.value) return
        viewModelScope.launch {
            _isSyncing.value = true
            zoneRepository.syncFromServer()
            _isSyncing.value = false
        }
    }

    fun toggleMapHeadingUp() {
        viewModelScope.launch {
            val current = settingsRepository.mapHeadingUp.first()
            settingsRepository.setMapHeadingUp(!current)
        }
    }

    private fun clockTicker(intervalMs: Long): Flow<Long> = flow {
        while (true) {
            emit(System.currentTimeMillis())
            delay(intervalMs)
        }
    }

    private companion object {
        const val THEME_TICK_MS: Long = 60_000L
        const val HYSTERESIS_MARGIN_DEG: Double = 0.5
    }
}

data class MapCameraSnapshot(
    val lat: Double,
    val lng: Double,
    val zoom: Double,
    val bearing: Double,
    val tilt: Double,
)
