// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.viewmodel

import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.demosten.srednabg.app.data.MapRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.service.LocationTrackingService
import com.demosten.srednabg.core.ZoneState
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    zoneRepository: ZoneRepository,
    private val mapRepository: MapRepository,
    @ApplicationContext private val context: Context,
) : ViewModel() {

    val zoneState: StateFlow<ZoneState> = LocationTrackingService.zoneState

    val isTracking: StateFlow<Boolean> = LocationTrackingService.isTracking

    val currentSpeedKmh: StateFlow<Double?> = LocationTrackingService.currentPosition
        .map { it?.speed }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    val zoneCount: StateFlow<Int> = zoneRepository.zones
        .map { it.size }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 0)

    init {
        viewModelScope.launch { zoneRepository.ensureLoaded() }
        viewModelScope.launch { mapRepository.ensureLoaded() }
    }

    fun startTracking() {
        val intent = Intent(context, LocationTrackingService::class.java)
        ContextCompat.startForegroundService(context, intent)
    }

    fun stopTracking() {
        val intent = Intent(context, LocationTrackingService::class.java)
        context.stopService(intent)
    }
}
