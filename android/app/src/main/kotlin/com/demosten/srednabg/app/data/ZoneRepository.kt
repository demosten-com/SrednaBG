// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import android.content.Context
import com.demosten.srednabg.app.data.local.ZoneDao
import com.demosten.srednabg.app.data.local.toEntity
import com.demosten.srednabg.app.data.local.toCoreZone
import com.demosten.srednabg.app.data.remote.ZoneApi
import com.demosten.srednabg.app.data.remote.ZonesResponse
import com.demosten.srednabg.core.Zone
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import dagger.hilt.android.qualifiers.ApplicationContext
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
        if (zoneDao.count() > 0) return
        loadFromAssets()
    }

    suspend fun syncFromServer(): SyncResult {
        return try {
            val version = zoneApi.fetchVersion()
            val cachedHash = settingsRepository.cachedZoneHash.first()
            if (version.hash == cachedHash && cachedHash.isNotEmpty()) return SyncResult.UpToDate

            val response = zoneApi.fetchZones()
            val entities = response.zones.map { it.toEntity(gson) }
            zoneDao.replaceAll(entities)
            settingsRepository.setCachedZoneHash(response.hash)
            SyncResult.Updated
        } catch (e: Exception) {
            SyncResult.Failed(e)
        }
    }

    private suspend fun loadFromAssets() {
        try {
            val json = context.assets.open("zones.json").bufferedReader().use { it.readText() }
            val response: ZonesResponse = gson.fromJson(json, object : TypeToken<ZonesResponse>() {}.type)
            if (response.zones.isNotEmpty()) {
                val entities = response.zones.map { it.toEntity(gson) }
                zoneDao.replaceAll(entities)
                settingsRepository.setCachedZoneHash(response.hash)
            }
        } catch (_: Exception) {
            // Asset file may be empty or malformed — that's OK, sync will fetch later
        }
    }
}
