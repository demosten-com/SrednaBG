// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.debug

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.location.Location
import android.os.Build
import android.os.SystemClock
import android.util.Log
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.content.ContextCompat
import androidx.core.os.LocaleListCompat
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.service.LocationTrackingService
import com.demosten.srednabg.core.MapThemeMode
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject

/**
 * Debug-only: harness control surface for the QA orchestrator.
 *
 * Two responsibilities — both are needed by the QA harness and neither
 * fits into [DebugSyncReceiver] which is purpose-built for sync:
 *
 *  1. **Settings injection** — flip any user-settable preference via a
 *     broadcast intent. Goes through [SettingsRepository]'s typed
 *     setters, the same code path the UI uses, so DataStore's
 *     single-writer queue is respected.
 *
 *  2. **Tracking lifecycle** — start / stop the foreground
 *     [LocationTrackingService]. The service is `exported="false"` in
 *     the production manifest, so `am start-foreground-service` from
 *     adb is blocked. Routing through this receiver lets the harness
 *     drive the full GPS pipeline without a UI tap.
 *
 * Examples (debug build only):
 *
 *     adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
 *         -a com.demosten.srednabg.debug.SET_SETTING --es key vehicle_type --es value truck
 *
 *     adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
 *         -a com.demosten.srednabg.debug.START_TRACKING
 *
 *     adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
 *         -a com.demosten.srednabg.debug.STOP_TRACKING
 *
 * Logs every applied change under tag [TAG] so the harness's logcat
 * parser can confirm the intent landed.
 */
@AndroidEntryPoint
class DebugControlReceiver : BroadcastReceiver() {

    @Inject lateinit var settings: SettingsRepository

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_SET_SETTING -> handleSetSetting(intent)
            ACTION_START_TRACKING -> handleStartTracking(context)
            ACTION_STOP_TRACKING -> handleStopTracking(context)
            ACTION_FEED_POINT -> handleFeedPoint(intent)
            else -> Log.w(TAG, "unknown action: ${intent.action}")
        }
    }

    private fun handleFeedPoint(intent: Intent) {
        val injector = LocationTrackingService.debugInjector ?: run {
            Log.w(TAG, "FEED_POINT: LocationTrackingService not running (start it first)")
            return
        }
        val lat = intent.getStringExtra("lat")?.toDoubleOrNull()
        val lng = intent.getStringExtra("lng")?.toDoubleOrNull()
        if (lat == null || lng == null) {
            Log.w(TAG, "FEED_POINT missing lat/lng")
            return
        }
        val speedMs = intent.getStringExtra("speed_ms")?.toFloatOrNull() ?: 0f
        val bearing = intent.getStringExtra("bearing")?.toFloatOrNull()
        val location = Location("debug-gpx").apply {
            latitude = lat
            longitude = lng
            speed = speedMs
            if (bearing != null) this.bearing = bearing
            accuracy = 5f
            time = System.currentTimeMillis()
            elapsedRealtimeNanos = SystemClock.elapsedRealtimeNanos()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) isMock = true
        }
        injector(location)
        Log.i(TAG, "feed lat=$lat lng=$lng speed=${speedMs}m/s bearing=$bearing")
    }

    private fun handleSetSetting(intent: Intent) {
        val key = intent.getStringExtra(EXTRA_KEY) ?: run {
            Log.w(TAG, "SET_SETTING missing extra key")
            return
        }
        val raw = intent.getStringExtra(EXTRA_VALUE) ?: run {
            Log.w(TAG, "SET_SETTING missing extra value (key=$key)")
            return
        }
        val pendingResult = goAsync()
        scope.launch {
            try {
                applySetting(key, raw)
                Log.i(TAG, "set $key=$raw")
            } catch (e: Exception) {
                Log.e(TAG, "set $key=$raw FAILED: ${e.message}", e)
            } finally {
                pendingResult.finish()
            }
        }
    }

    private suspend fun applySetting(key: String, raw: String) {
        when (key) {
            "vehicle_type" -> settings.setVehicleType(raw)
            "app_language" -> {
                settings.setAppLanguage(raw)
                val tags = if (raw == "system") "" else raw
                withContext(Dispatchers.Main) {
                    AppCompatDelegate.setApplicationLocales(
                        LocaleListCompat.forLanguageTags(tags),
                    )
                }
            }
            "voice_enabled" -> settings.setVoiceEnabled(raw.toBooleanStrict())
            "periodic_voice_updates" -> settings.setPeriodicVoiceUpdates(raw.toBooleanStrict())
            "announce_only_when_over" -> settings.setAnnounceOnlyWhenOver(raw.toBooleanStrict())
            "alert_threshold_kmh" -> settings.setAlertThreshold(raw.toInt())
            "map_heading_up" -> settings.setMapHeadingUp(raw.toBooleanStrict())
            "map_theme_mode" -> settings.setMapThemeMode(MapThemeMode.valueOf(raw.uppercase()))
            "cached_zone_hash" -> settings.setCachedZoneHash(raw)
            "cached_map_hash" -> settings.setCachedMapHash(raw)
            else -> throw IllegalArgumentException("unknown setting key: $key")
        }
    }

    private fun handleStartTracking(context: Context) {
        val intent = Intent(context, LocationTrackingService::class.java)
        ContextCompat.startForegroundService(context, intent)
        Log.i(TAG, "start tracking")
    }

    private fun handleStopTracking(context: Context) {
        val intent = Intent(context, LocationTrackingService::class.java)
        context.stopService(intent)
        Log.i(TAG, "stop tracking")
    }

    companion object {
        private const val TAG = "DebugSettings"
        const val ACTION_SET_SETTING = "com.demosten.srednabg.debug.SET_SETTING"
        const val ACTION_START_TRACKING = "com.demosten.srednabg.debug.START_TRACKING"
        const val ACTION_STOP_TRACKING = "com.demosten.srednabg.debug.STOP_TRACKING"
        const val ACTION_FEED_POINT = "com.demosten.srednabg.debug.FEED_POINT"
        const val EXTRA_KEY = "key"
        const val EXTRA_VALUE = "value"
    }
}
