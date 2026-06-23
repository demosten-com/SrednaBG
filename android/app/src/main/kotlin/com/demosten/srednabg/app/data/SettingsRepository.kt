// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import com.demosten.srednabg.core.MapThemeMode
import java.util.Locale
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SettingsRepository @Inject constructor(
    private val dataStore: DataStore<Preferences>,
) {
    companion object {
        private val KEY_VOICE_ENABLED = booleanPreferencesKey("voice_enabled")
        private val KEY_PERIODIC_VOICE_UPDATES = booleanPreferencesKey("periodic_voice_updates")
        private val KEY_ANNOUNCE_ONLY_WHEN_OVER = booleanPreferencesKey("announce_only_when_over")
        private val KEY_APP_LANGUAGE = stringPreferencesKey("app_language")
        private val KEY_VEHICLE_TYPE = stringPreferencesKey("vehicle_type")
        private val KEY_ZONE_HASH = stringPreferencesKey("cached_zone_hash")
        private val KEY_ZONE_VERSION = stringPreferencesKey("cached_zone_version")
        private val KEY_MAP_HASH = stringPreferencesKey("cached_map_hash")
        private val KEY_MAP_HEADING_UP = booleanPreferencesKey("map_heading_up")
        private val KEY_MAP_THEME_MODE = stringPreferencesKey("map_theme_mode")
        private val KEY_MAP_ZOOM_OVERRIDE = floatPreferencesKey("map_zoom_override")
        // Screenshot harness only: when set, in-zone UI shows this value for
        // "Max now" instead of the live SpeedStatus computation. Lets the
        // App Store / Play Store harness render a meaningful number even when
        // the live calc would land at the 250 cap or near 0.
        private val KEY_DEBUG_MAX_SPEED_OVERRIDE = intPreferencesKey("debug_max_speed_override")
        private val KEY_AUTO_STOP_HOURS = intPreferencesKey("auto_stop_hours")
        // QA harness only: when > 0, the inactivity timer compares against
        // this value in seconds instead of `auto_stop_hours * 3600` so the
        // scenario can fire in ~10 s instead of 3 h. Mirrors the
        // `debug_max_speed_override` shape (DEBUG broadcast only).
        private val KEY_DEBUG_AUTO_STOP_SECONDS = intPreferencesKey("debug_auto_stop_seconds")
        private val KEY_ZONE_SYNC_ENABLED = booleanPreferencesKey("zone_sync_enabled")
        // Floating system overlay (draw-on-top of Waze/Maps). Opt-in, default
        // off; the live position is persisted so the user's drag survives
        // restarts. -1 sentinel = "not yet positioned" (controller picks a
        // sensible default the first time it shows).
        private val KEY_OVERLAY_ENABLED = booleanPreferencesKey("overlay_enabled")
        private val KEY_OVERLAY_POS_X = intPreferencesKey("overlay_pos_x")
        private val KEY_OVERLAY_POS_Y = intPreferencesKey("overlay_pos_y")

        const val DEFAULT_APP_LANGUAGE = "system"
        const val DEFAULT_VEHICLE_TYPE = "car"
        const val DEFAULT_PERIODIC_VOICE_UPDATES = true
        const val DEFAULT_ANNOUNCE_ONLY_WHEN_OVER = true
        const val DEFAULT_AUTO_STOP_HOURS = 3
        const val DEFAULT_ZONE_SYNC_ENABLED = true
        const val DEFAULT_OVERLAY_ENABLED = false
        const val OVERLAY_POS_UNSET = -1
        val DEFAULT_MAP_THEME_MODE: MapThemeMode = MapThemeMode.AUTO

        const val LANG_SYSTEM = "system"
        const val LANG_BG = "bg"
        const val LANG_EN = "en"
    }

    val voiceEnabled: Flow<Boolean> = dataStore.data.map { prefs ->
        prefs[KEY_VOICE_ENABLED] ?: true
    }

    val periodicVoiceUpdates: Flow<Boolean> = dataStore.data.map { prefs ->
        prefs[KEY_PERIODIC_VOICE_UPDATES] ?: DEFAULT_PERIODIC_VOICE_UPDATES
    }

    val announceOnlyWhenOver: Flow<Boolean> = dataStore.data.map { prefs ->
        prefs[KEY_ANNOUNCE_ONLY_WHEN_OVER] ?: DEFAULT_ANNOUNCE_ONLY_WHEN_OVER
    }

    val appLanguage: Flow<String> = dataStore.data.map { prefs ->
        prefs[KEY_APP_LANGUAGE] ?: DEFAULT_APP_LANGUAGE
    }

    val voiceLanguage: Flow<String> = appLanguage.map { resolveVoiceLanguage(it) }

    val vehicleType: Flow<String> = dataStore.data.map { prefs ->
        prefs[KEY_VEHICLE_TYPE] ?: DEFAULT_VEHICLE_TYPE
    }

    val cachedZoneHash: Flow<String> = dataStore.data.map { prefs ->
        prefs[KEY_ZONE_HASH] ?: ""
    }

    val cachedZoneVersion: Flow<String> = dataStore.data.map { prefs ->
        prefs[KEY_ZONE_VERSION] ?: ""
    }

    val cachedMapHash: Flow<String> = dataStore.data.map { prefs ->
        prefs[KEY_MAP_HASH] ?: ""
    }

    val mapHeadingUp: Flow<Boolean> = dataStore.data.map { prefs ->
        prefs[KEY_MAP_HEADING_UP] ?: false
    }

    val mapThemeMode: Flow<MapThemeMode> = dataStore.data.map { prefs ->
        prefs[KEY_MAP_THEME_MODE]?.let { runCatching { MapThemeMode.valueOf(it) }.getOrNull() }
            ?: DEFAULT_MAP_THEME_MODE
    }

    val mapZoomOverride: Flow<Float?> = dataStore.data.map { prefs ->
        prefs[KEY_MAP_ZOOM_OVERRIDE]
    }

    val debugMaxSpeedOverride: Flow<Int?> = dataStore.data.map { prefs ->
        prefs[KEY_DEBUG_MAX_SPEED_OVERRIDE]
    }

    val autoStopHours: Flow<Int> = dataStore.data.map { prefs ->
        prefs[KEY_AUTO_STOP_HOURS] ?: DEFAULT_AUTO_STOP_HOURS
    }

    val debugAutoStopSeconds: Flow<Int?> = dataStore.data.map { prefs ->
        prefs[KEY_DEBUG_AUTO_STOP_SECONDS]
    }

    val zoneSyncEnabled: Flow<Boolean> = dataStore.data.map { prefs ->
        prefs[KEY_ZONE_SYNC_ENABLED] ?: DEFAULT_ZONE_SYNC_ENABLED
    }

    val overlayEnabled: Flow<Boolean> = dataStore.data.map { prefs ->
        prefs[KEY_OVERLAY_ENABLED] ?: DEFAULT_OVERLAY_ENABLED
    }

    val overlayPosX: Flow<Int> = dataStore.data.map { prefs ->
        prefs[KEY_OVERLAY_POS_X] ?: OVERLAY_POS_UNSET
    }

    val overlayPosY: Flow<Int> = dataStore.data.map { prefs ->
        prefs[KEY_OVERLAY_POS_Y] ?: OVERLAY_POS_UNSET
    }

    suspend fun setVoiceEnabled(value: Boolean) {
        dataStore.edit { it[KEY_VOICE_ENABLED] = value }
    }

    suspend fun setPeriodicVoiceUpdates(value: Boolean) {
        dataStore.edit { it[KEY_PERIODIC_VOICE_UPDATES] = value }
    }

    suspend fun setAnnounceOnlyWhenOver(value: Boolean) {
        dataStore.edit { it[KEY_ANNOUNCE_ONLY_WHEN_OVER] = value }
    }

    suspend fun setAppLanguage(value: String) {
        dataStore.edit { it[KEY_APP_LANGUAGE] = value }
    }

    suspend fun setVehicleType(value: String) {
        dataStore.edit { it[KEY_VEHICLE_TYPE] = value }
    }

    suspend fun setCachedZoneHash(value: String) {
        dataStore.edit { it[KEY_ZONE_HASH] = value }
    }

    suspend fun setCachedZoneVersion(value: String) {
        dataStore.edit { it[KEY_ZONE_VERSION] = value }
    }

    suspend fun setCachedMapHash(value: String) {
        dataStore.edit { it[KEY_MAP_HASH] = value }
    }

    suspend fun setMapHeadingUp(value: Boolean) {
        dataStore.edit { it[KEY_MAP_HEADING_UP] = value }
    }

    suspend fun setMapThemeMode(value: MapThemeMode) {
        dataStore.edit { it[KEY_MAP_THEME_MODE] = value.name }
    }

    suspend fun setMapZoomOverride(value: Float?) {
        dataStore.edit { p ->
            if (value == null) {
                p.remove(KEY_MAP_ZOOM_OVERRIDE)
            } else {
                p[KEY_MAP_ZOOM_OVERRIDE] = value
            }
        }
    }

    suspend fun setDebugMaxSpeedOverride(value: Int?) {
        dataStore.edit { p ->
            if (value == null) {
                p.remove(KEY_DEBUG_MAX_SPEED_OVERRIDE)
            } else {
                p[KEY_DEBUG_MAX_SPEED_OVERRIDE] = value
            }
        }
    }

    suspend fun setAutoStopHours(value: Int) {
        dataStore.edit { it[KEY_AUTO_STOP_HOURS] = value }
    }

    suspend fun setDebugAutoStopSeconds(value: Int?) {
        dataStore.edit { p ->
            if (value == null || value <= 0) {
                p.remove(KEY_DEBUG_AUTO_STOP_SECONDS)
            } else {
                p[KEY_DEBUG_AUTO_STOP_SECONDS] = value
            }
        }
    }

    suspend fun setZoneSyncEnabled(value: Boolean) {
        dataStore.edit { it[KEY_ZONE_SYNC_ENABLED] = value }
    }

    suspend fun setOverlayEnabled(value: Boolean) {
        dataStore.edit { it[KEY_OVERLAY_ENABLED] = value }
    }

    suspend fun setOverlayPosition(x: Int, y: Int) {
        dataStore.edit {
            it[KEY_OVERLAY_POS_X] = x
            it[KEY_OVERLAY_POS_Y] = y
        }
    }
}

private fun resolveVoiceLanguage(app: String): String = when (app) {
    SettingsRepository.LANG_BG -> SettingsRepository.LANG_BG
    SettingsRepository.LANG_EN -> SettingsRepository.LANG_EN
    else -> if (Locale.getDefault().language == SettingsRepository.LANG_BG) {
        SettingsRepository.LANG_BG
    } else {
        SettingsRepository.LANG_EN
    }
}
