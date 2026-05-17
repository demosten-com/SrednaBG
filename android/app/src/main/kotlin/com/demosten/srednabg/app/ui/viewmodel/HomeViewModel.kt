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
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.permissions.PermissionRepository
import com.demosten.srednabg.app.permissions.PermissionState
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
    private val permissionRepository: PermissionRepository,
    settingsRepository: SettingsRepository,
    @ApplicationContext private val context: Context,
) : ViewModel() {

    val debugMaxSpeedOverride: StateFlow<Int?> = settingsRepository.debugMaxSpeedOverride
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    val zoneState: StateFlow<ZoneState> = LocationTrackingService.zoneState

    val isTracking: StateFlow<Boolean> = LocationTrackingService.isTracking

    val currentSpeedKmh: StateFlow<Double?> = LocationTrackingService.currentPosition
        .map { it?.speed }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    val zoneCount: StateFlow<Int> = zoneRepository.zones
        .map { it.size }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 0)

    val permissionState: StateFlow<PermissionState> = permissionRepository.state

    init {
        viewModelScope.launch { zoneRepository.ensureLoaded() }
        viewModelScope.launch { mapRepository.ensureLoaded() }
    }

    /** Re-check OS permission + battery-opt state. Hooked to `ON_RESUME` from
     *  `HomeScreen` so a user toggling the permission in Settings sees the
     *  permission card disappear the moment they return to the app. */
    fun refreshPermissions() {
        permissionRepository.refresh()
    }

    /**
     * Start the foreground service if (and only if) the OS permissions a
     * sustained tracking session needs are all granted. The HomeScreen
     * normally hides the Start button in the missing-permission state, but
     * the gate is also enforced here so a debug intent or a future caller
     * can't bypass it and bring up a tracking session that silently dies
     * the moment the screen locks.
     */
    fun startTracking() {
        if (!permissionRepository.state.value.canStartTracking) return
        val intent = Intent(context, LocationTrackingService::class.java)
        ContextCompat.startForegroundService(context, intent)
    }

    fun stopTracking() {
        val intent = Intent(context, LocationTrackingService::class.java)
        context.stopService(intent)
    }
}
