// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.permissions

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.content.ContextCompat
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Snapshot of every OS-level permission + power-management knob that affects
 * sustained background tracking. Mirrors the iOS `LocationPermission` shape
 * but expanded to cover Android's three-permission story (foreground +
 * background + notifications) plus battery-optimization whitelisting, which
 * iOS doesn't have an equivalent of.
 */
data class PermissionState(
    val fineLocationGranted: Boolean = false,
    val backgroundLocationGranted: Boolean = false,
    val notificationGranted: Boolean = false,
    val ignoringBatteryOptimizations: Boolean = false,
    val canDrawOverlays: Boolean = false,
) {
    /**
     * The two OS permissions a tracking session must have. `POST_NOTIFICATIONS`
     * is intentionally not part of the gate: on T+ the foreground-service
     * notification will be hidden without it, which OEM kill daemons may treat
     * as license to stop the process — but that's a *reliability* warning, not
     * a hard blocker. Forcing notifications into the gate stranded users who
     * declined them on the OS prompt with no way out except Settings, even
     * after they had granted the actual location permissions. The Home screen
     * surfaces a dedicated "Notifications recommended" card that explains the
     * trade-off and lets the user grant from inside the app.
     */
    val canStartTracking: Boolean
        get() = fineLocationGranted && backgroundLocationGranted
}

/**
 * Single source of truth for runtime permissions + battery-optimization
 * status. Singleton so the prompt-driving Composable
 * (`PermissionHandler`) and the gate inside `HomeViewModel` see the
 * same state without an event bus.
 */
@Singleton
class PermissionRepository @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val _state = MutableStateFlow(snapshot())
    val state: StateFlow<PermissionState> = _state.asStateFlow()

    /** Re-read every permission + battery-opt flag from the OS. Call from
     *  `Lifecycle.Event.ON_RESUME` so changes the user made in Settings while
     *  the app was backgrounded show up immediately. */
    fun refresh() {
        _state.value = snapshot()
    }

    private fun snapshot(): PermissionState = PermissionState(
        fineLocationGranted = isGranted(Manifest.permission.ACCESS_FINE_LOCATION),
        backgroundLocationGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            isGranted(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        } else {
            // Pre-Q: background access was granted implicitly alongside fine
            // location — there's no separate permission to check, and
            // `checkSelfPermission` on the string would return DENIED and
            // soft-brick the gate.
            true
        },
        notificationGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            isGranted(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            true
        },
        ignoringBatteryOptimizations = isIgnoringBatteryOptimizations(),
        canDrawOverlays = Settings.canDrawOverlays(context),
    )

    private fun isGranted(permission: String): Boolean =
        ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

    private fun isIgnoringBatteryOptimizations(): Boolean {
        val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return false
        return pm.isIgnoringBatteryOptimizations(context.packageName)
    }
}
