// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import android.content.Context
import android.content.res.AssetManager
import com.demosten.srednabg.app.data.local.ZoneDao
import com.demosten.srednabg.app.data.local.ZoneEntity
import com.demosten.srednabg.app.data.remote.VersionResponse
import com.demosten.srednabg.app.data.remote.ZoneApi
import com.demosten.srednabg.app.data.remote.ZonesResponse
import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import com.google.gson.Gson
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import java.io.ByteArrayInputStream
import java.io.IOException

class ZoneRepositoryTest {

    private lateinit var zoneDao: ZoneDao
    private lateinit var zoneApi: ZoneApi
    private lateinit var settingsRepository: SettingsRepository
    private lateinit var context: Context
    private lateinit var repository: ZoneRepository
    private val gson = Gson()

    private val testZone = Zone(
        id = "test-zone",
        road = "Test Road",
        roadLatin = "Test Road",
        direction = "east",
        description = "Test",
        start = ZoneEndpoint(lat = 42.0, lng = 23.0),
        end = ZoneEndpoint(lat = 42.1, lng = 23.1),
        distanceM = 5000,
        speedLimits = SpeedLimits(car = 120, truck = 80, bus = 90),
        centerline = listOf(listOf(42.0, 23.0), listOf(42.1, 23.1)),
        source = "test",
        lastVerified = "2026-04-12",
    )

    @BeforeEach
    fun setUp() {
        zoneDao = mockk(relaxed = true)
        zoneApi = mockk()
        settingsRepository = mockk(relaxed = true)
        context = mockk()

        every { zoneDao.getAllZones() } returns flowOf(emptyList())

        repository = ZoneRepository(zoneDao, zoneApi, settingsRepository, gson, context)
    }

    @Test
    fun `ensureLoaded skips loading when database has zones`() = runTest {
        coEvery { zoneDao.count() } returns 10

        repository.ensureLoaded()

        coVerify(exactly = 0) { zoneDao.replaceAll(any()) }
    }

    @Test
    fun `ensureLoaded loads from assets when database is empty`() = runTest {
        coEvery { zoneDao.count() } returns 0

        val zonesJson = gson.toJson(ZonesResponse("v1", "hash123", listOf(testZone)))
        val assetManager = mockk<AssetManager>()
        every { context.assets } returns assetManager
        every { assetManager.open("zones.json") } returns ByteArrayInputStream(zonesJson.toByteArray())

        repository.ensureLoaded()

        coVerify { zoneDao.replaceAll(any()) }
        coVerify { settingsRepository.setCachedZoneHash("hash123") }
        coVerify { settingsRepository.setCachedZoneVersion("v1") }
    }

    @Test
    fun `syncFromServer returns UpToDate when hash matches`() = runTest {
        coEvery { zoneApi.fetchVersion() } returns VersionResponse("v1", "samehash", null, 1)
        coEvery { settingsRepository.cachedZoneHash } returns flowOf("samehash")

        val result = repository.syncFromServer()

        assertEquals(SyncResult.UpToDate, result)
        coVerify(exactly = 0) { zoneApi.fetchZones() }
        // Backfills the version for installs that cached only the hash.
        coVerify { settingsRepository.setCachedZoneVersion("v1") }
    }

    @Test
    fun `syncFromServer returns Updated when zones replaced`() = runTest {
        coEvery { zoneApi.fetchVersion() } returns VersionResponse("v1", "newhash", null, 1)
        coEvery { settingsRepository.cachedZoneHash } returns flowOf("oldhash")
        coEvery { zoneApi.fetchZones() } returns ZonesResponse("v1", "newhash", listOf(testZone))

        val result = repository.syncFromServer()

        assertEquals(SyncResult.Updated, result)
        coVerify { zoneDao.replaceAll(any()) }
        coVerify { settingsRepository.setCachedZoneHash("newhash") }
        coVerify { settingsRepository.setCachedZoneVersion("v1") }
    }

    @Test
    fun `syncFromServer returns Failed on network error`() = runTest {
        coEvery { zoneApi.fetchVersion() } throws IOException("Network error")

        val result = repository.syncFromServer()

        assertTrue(result is SyncResult.Failed)
    }

    @Test
    fun `syncFromServer fetches zones when cached hash is empty`() = runTest {
        coEvery { zoneApi.fetchVersion() } returns VersionResponse("v1", "hash1", null, 1)
        coEvery { settingsRepository.cachedZoneHash } returns flowOf("")
        coEvery { zoneApi.fetchZones() } returns ZonesResponse("v1", "hash1", listOf(testZone))

        val result = repository.syncFromServer()

        assertEquals(SyncResult.Updated, result)
        coVerify { zoneApi.fetchZones() }
    }
}
