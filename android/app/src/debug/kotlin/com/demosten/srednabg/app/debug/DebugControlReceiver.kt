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
import com.demosten.srednabg.app.data.HistoryRepository
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.service.LocationTrackingService
import com.demosten.srednabg.core.MapThemeMode
import com.google.gson.Gson
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
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
    @Inject lateinit var historyRepository: HistoryRepository
    @Inject lateinit var zoneRepository: ZoneRepository
    @Inject lateinit var gson: Gson

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_SET_SETTING -> handleSetSetting(intent)
            ACTION_START_TRACKING -> handleStartTracking(context)
            ACTION_STOP_TRACKING -> handleStopTracking(context)
            ACTION_FEED_POINT -> handleFeedPoint(intent)
            ACTION_DUMP_HISTORY -> handleDumpHistory()
            ACTION_SEED_HISTORY -> handleSeedHistory(intent)
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
        // Optional simulated fix time (epoch ms). Lets a QA harness feed a route
        // far faster than wall-clock while still presenting realistic ~1 s fix
        // spacing to the GPS pipeline: the Kalman filter and speed inference use
        // location.time deltas, so injecting hundreds of fixes a few ms apart in
        // real time but stamped 1 s apart keeps the filter tracking (a tiny dt
        // makes its process noise vanish → the smoothed dot lags off the road on
        // bends → spurious off-road exits). elapsedRealtimeNanos stays "now" so
        // the service's fix-freshness check still passes.
        val timeMs = intent.getStringExtra("time_ms")?.toLongOrNull() ?: System.currentTimeMillis()
        // Optional reported accuracy (meters). Defaults to a clean 5 m so existing
        // scenarios are unaffected; a QA scenario can pass a coarse value to
        // exercise the service's MAX_ACCURACY_M gate (the noisy-fix regression).
        val accuracyM = intent.getStringExtra("accuracy")?.toFloatOrNull() ?: 5f
        val location = Location("debug-gpx").apply {
            latitude = lat
            longitude = lng
            speed = speedMs
            if (bearing != null) this.bearing = bearing
            accuracy = accuracyM
            time = timeMs
            elapsedRealtimeNanos = SystemClock.elapsedRealtimeNanos()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) isMock = true
        }
        injector(location)
        Log.i(TAG, "feed lat=$lat lng=$lng speed=${speedMs}m/s bearing=$bearing accuracy=${accuracyM}m")
    }

    /**
     * QA introspection: log the history record count plus a one-line summary of
     * the most recent traversal under [TAG], so the harness can assert on history
     * without reading the Room DB directly. All fields are on a single, easily
     * grepped line prefixed `DUMP_HISTORY`.
     */
    private fun handleDumpHistory() {
        val pendingResult = goAsync()
        scope.launch {
            try {
                val count = historyRepository.count()
                val latest = historyRepository.latest()
                if (latest == null) {
                    Log.i(TAG, "DUMP_HISTORY count=$count latest=none")
                } else {
                    Log.i(
                        TAG,
                        "DUMP_HISTORY count=$count zone=${latest.zoneId} " +
                            "avg=${latest.avgSpeedKmh} min=${latest.sustainedMinKmh} " +
                            "max=${latest.sustainedMaxKmh} over=${latest.isOverLimit} " +
                            "limit=${latest.speedLimitKmh} vehicle=${latest.vehicleType} " +
                            "entry=${latest.entryTimeMs} exit=${latest.exitTimeMs}",
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "DUMP_HISTORY failed: ${e.message}", e)
            } finally {
                pendingResult.finish()
            }
        }
    }

    /**
     * Wipe the History DB and refill it with a curated set of varied sample
     * traversals (default 12; override with `--es count N`) so a developer can
     * browse the History tab + detail graph without driving every zone. Uses the
     * app's loaded zones for real roads. Android peer of iOS's
     * `/history?action=seed`. See [HistorySeeder].
     */
    private fun handleSeedHistory(intent: Intent) {
        val count = intent.getStringExtra("count")?.toIntOrNull() ?: DEFAULT_SEED_COUNT
        val pendingResult = goAsync()
        scope.launch {
            try {
                zoneRepository.ensureLoaded()
                val zones = zoneRepository.zones.first()
                val inserted = HistorySeeder.seed(
                    historyRepository = historyRepository,
                    gson = gson,
                    zones = zones,
                    count = count,
                    nowMs = System.currentTimeMillis(),
                )
                Log.i(TAG, "SEED_HISTORY inserted=$inserted (requested=$count, zones=${zones.size})")
            } catch (e: Exception) {
                Log.e(TAG, "SEED_HISTORY failed: ${e.message}", e)
            } finally {
                pendingResult.finish()
            }
        }
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
            "map_heading_up" -> settings.setMapHeadingUp(raw.toBooleanStrict())
            "map_theme_mode" -> settings.setMapThemeMode(MapThemeMode.valueOf(raw.uppercase()))
            "map_zoom_override" -> settings.setMapZoomOverride(raw.toFloatOrNull())
            "debug_max_speed_override" -> settings.setDebugMaxSpeedOverride(raw.toIntOrNull())
            "auto_stop_hours" -> settings.setAutoStopHours(raw.toInt())
            "history_retention" -> settings.setHistoryRetention(raw)
            "debug_auto_stop_seconds" -> settings.setDebugAutoStopSeconds(raw.toIntOrNull())
            "cached_zone_hash" -> settings.setCachedZoneHash(raw)
            "cached_zone_version" -> settings.setCachedZoneVersion(raw)
            "cached_map_hash" -> settings.setCachedMapHash(raw)
            "zone_sync_enabled" -> settings.setZoneSyncEnabled(raw.toBooleanStrict())
            "overlay_enabled" -> settings.setOverlayEnabled(raw.toBooleanStrict())
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
        const val ACTION_DUMP_HISTORY = "com.demosten.srednabg.debug.DUMP_HISTORY"
        const val ACTION_SEED_HISTORY = "com.demosten.srednabg.debug.SEED_HISTORY"
        const val EXTRA_KEY = "key"
        const val EXTRA_VALUE = "value"
        private const val DEFAULT_SEED_COUNT = 12
    }
}
