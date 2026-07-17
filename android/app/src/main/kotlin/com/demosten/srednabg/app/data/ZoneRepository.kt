// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import android.content.Context
import android.util.Log
import com.demosten.srednabg.app.data.local.ZoneDao
import com.demosten.srednabg.app.data.local.toEntity
import com.demosten.srednabg.app.data.local.toCoreZone
import com.demosten.srednabg.app.data.remote.ZoneApi
import com.demosten.srednabg.app.data.remote.ZonesResponse
import com.demosten.srednabg.core.Zone
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

sealed class SyncResult {
    data object Updated : SyncResult()
    data object UpToDate : SyncResult()
    data class Failed(val cause: Throwable?) : SyncResult()
}

@Singleton
class ZoneRepository @Inject constructor(
    private val zoneDao: ZoneDao,
    private val zoneApi: ZoneApi,
    private val settingsRepository: SettingsRepository,
    private val gson: Gson,
    @ApplicationContext private val context: Context,
) {
    val zones: Flow<List<Zone>> = zoneDao.getAllZones().map { entities ->
        entities.map { it.toCoreZone(gson) }
    }

    suspend fun ensureLoaded() {
        if (zoneDao.count() > 0) {
            maybeReseedFromAssets()
            return
        }
        loadFromAssets()
    }

    suspend fun syncFromServer(): SyncResult {
        return try {
            val version = zoneApi.fetchVersion()
            val cachedHash = settingsRepository.cachedZoneHash.first()
            val cachedVersion = settingsRepository.cachedZoneVersion.first()
            when (ZoneDataRecency.decide(version.hash, version.version, cachedHash, cachedVersion)) {
                ZoneSyncDecision.UP_TO_DATE -> {
                    // Backfill for installs that cached the hash before the
                    // version timestamp existed — same data, so same version.
                    settingsRepository.setCachedZoneVersion(version.version)
                    SyncResult.UpToDate
                }
                ZoneSyncDecision.SKIP_REMOTE_STALE -> {
                    // A locally built app can bundle a fresher scrape than the
                    // weekly server cron — the server must never downgrade us.
                    Log.i(
                        TAG,
                        "Skipping zone sync: server data ${version.version} is not newer than local $cachedVersion",
                    )
                    SyncResult.UpToDate
                }
                ZoneSyncDecision.APPLY_REMOTE -> {
                    val response = zoneApi.fetchZones()
                    val entities = response.zones.map { it.toEntity(gson) }
                    zoneDao.replaceAll(entities)
                    settingsRepository.setCachedZoneHash(response.hash)
                    settingsRepository.setCachedZoneVersion(response.version)
                    SyncResult.Updated
                }
            }
        } catch (e: CancellationException) {
            // WorkManager cancellation — let the coroutine unwind rather than
            // mis-reporting it as a sync failure (which would trigger a retry).
            throw e
        } catch (e: Exception) {
            SyncResult.Failed(e)
        }
    }

    private suspend fun loadFromAssets() {
        val response = parseBundledZones() ?: return
        if (response.zones.isNotEmpty()) {
            val entities = response.zones.map { it.toEntity(gson) }
            zoneDao.replaceAll(entities)
            settingsRepository.setCachedZoneHash(response.hash)
            settingsRepository.setCachedZoneVersion(response.version)
        }
    }

    /**
     * App-upgrade path: the bundled zones.json can be fresher than the last
     * synced data (a release built from a scrape the weekly server cron
     * hasn't published yet), so a non-empty store still re-seeds when the
     * bundle is provably newer. Ordering vs the launch `ZoneSyncWorker` is
     * convergent either way: whichever of the two applies newer data first,
     * the other's recency gate then skips.
     */
    private suspend fun maybeReseedFromAssets() {
        if (bundleRecencyChecked) return
        bundleRecencyChecked = true
        val response = parseBundledZones() ?: return
        if (response.zones.isEmpty()) return
        val cachedHash = settingsRepository.cachedZoneHash.first()
        val cachedVersion = settingsRepository.cachedZoneVersion.first()
        if (!ZoneDataRecency.shouldReseedFromBundle(
                response.hash, response.version, cachedHash, cachedVersion,
            )
        ) {
            return
        }
        Log.i(TAG, "Re-seeding zones from bundle ${response.version} (local was $cachedVersion)")
        val entities = response.zones.map { it.toEntity(gson) }
        zoneDao.replaceAll(entities)
        settingsRepository.setCachedZoneHash(response.hash)
        settingsRepository.setCachedZoneVersion(response.version)
    }

    private fun parseBundledZones(): ZonesResponse? {
        return try {
            val json = context.assets.open("zones.json").bufferedReader().use { it.readText() }
            gson.fromJson(json, object : TypeToken<ZonesResponse>() {}.type)
        } catch (e: Exception) {
            // Asset file may be empty or malformed — recoverable (sync will fetch
            // later), but log it: a malformed generated zones.json would otherwise
            // leave the app with zero zones with no trace of why.
            Log.w(TAG, "Failed to load bundled zones.json; will rely on server sync", e)
            null
        }
    }

    /** Once per process — ensureLoaded() is called from several entry points. */
    @Volatile
    private var bundleRecencyChecked = false

    private companion object {
        const val TAG = "SrednaBG.ZoneRepo"
    }
}
