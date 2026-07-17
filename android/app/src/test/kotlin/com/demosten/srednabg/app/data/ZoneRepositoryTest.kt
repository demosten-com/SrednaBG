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
        // Relaxed mocks return a non-emitting Flow, on which `.first()` throws —
        // stub the cached-state reads the recency gate performs. Per-test stubs
        // override these defaults.
        every { settingsRepository.cachedZoneHash } returns flowOf("")
        every { settingsRepository.cachedZoneVersion } returns flowOf("")

        repository = ZoneRepository(zoneDao, zoneApi, settingsRepository, gson, context)
    }

    private fun stubBundledZones(version: String, hash: String) {
        val zonesJson = gson.toJson(ZonesResponse(version, hash, listOf(testZone)))
        val assetManager = mockk<AssetManager>()
        every { context.assets } returns assetManager
        every { assetManager.open("zones.json") } returns ByteArrayInputStream(zonesJson.toByteArray())
    }

    @Test
    fun `ensureLoaded skips loading when database has zones`() = runTest {
        coEvery { zoneDao.count() } returns 10
        stubBundledZones(version = "2026-07-17T11:51:47Z", hash = "samehash")
        every { settingsRepository.cachedZoneHash } returns flowOf("samehash")

        repository.ensureLoaded()

        coVerify(exactly = 0) { zoneDao.replaceAll(any()) }
    }

    @Test
    fun `ensureLoaded reseeds when bundled version is newer than cached`() = runTest {
        coEvery { zoneDao.count() } returns 10
        stubBundledZones(version = "2026-07-17T11:51:47Z", hash = "bundlehash")
        every { settingsRepository.cachedZoneHash } returns flowOf("oldhash")
        every { settingsRepository.cachedZoneVersion } returns flowOf("2026-07-13T06:10:40Z")

        repository.ensureLoaded()

        coVerify { zoneDao.replaceAll(any()) }
        coVerify { settingsRepository.setCachedZoneHash("bundlehash") }
        coVerify { settingsRepository.setCachedZoneVersion("2026-07-17T11:51:47Z") }
    }

    @Test
    fun `ensureLoaded skips reseed when bundled version is not newer`() = runTest {
        coEvery { zoneDao.count() } returns 10
        stubBundledZones(version = "2026-07-13T06:10:40Z", hash = "bundlehash")
        every { settingsRepository.cachedZoneHash } returns flowOf("newerhash")
        every { settingsRepository.cachedZoneVersion } returns flowOf("2026-07-17T11:51:47Z")

        repository.ensureLoaded()

        coVerify(exactly = 0) { zoneDao.replaceAll(any()) }
        coVerify(exactly = 0) { settingsRepository.setCachedZoneHash(any()) }
    }

    @Test
    fun `ensureLoaded checks bundle recency only once per process`() = runTest {
        coEvery { zoneDao.count() } returns 10
        stubBundledZones(version = "2026-07-17T11:51:47Z", hash = "bundlehash")
        every { settingsRepository.cachedZoneHash } returns flowOf("oldhash")
        every { settingsRepository.cachedZoneVersion } returns flowOf("2026-07-13T06:10:40Z")

        repository.ensureLoaded()
        repository.ensureLoaded()

        coVerify(exactly = 1) { zoneDao.replaceAll(any()) }
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

    @Test
    fun `syncFromServer skips fetch when remote version is older`() = runTest {
        coEvery { zoneApi.fetchVersion() } returns
            VersionResponse("2026-07-13T06:10:40Z", "serverhash", null, 1)
        every { settingsRepository.cachedZoneHash } returns flowOf("localhash")
        every { settingsRepository.cachedZoneVersion } returns flowOf("2026-07-17T11:51:47Z")

        val result = repository.syncFromServer()

        assertEquals(SyncResult.UpToDate, result)
        coVerify(exactly = 0) { zoneApi.fetchZones() }
        coVerify(exactly = 0) { settingsRepository.setCachedZoneHash(any()) }
        coVerify(exactly = 0) { settingsRepository.setCachedZoneVersion(any()) }
    }

    @Test
    fun `syncFromServer fetches when remote version equals cached with different hash`() = runTest {
        // Equal version + different hash = corrupted local state; the server
        // repairs it (also what lets QA poison the hash to force a re-fetch).
        coEvery { zoneApi.fetchVersion() } returns
            VersionResponse("2026-07-17T11:51:47Z", "serverhash", null, 1)
        every { settingsRepository.cachedZoneHash } returns flowOf("localhash")
        every { settingsRepository.cachedZoneVersion } returns flowOf("2026-07-17T11:51:47Z")
        coEvery { zoneApi.fetchZones() } returns
            ZonesResponse("2026-07-17T11:51:47Z", "serverhash", listOf(testZone))

        val result = repository.syncFromServer()

        assertEquals(SyncResult.Updated, result)
        coVerify { zoneApi.fetchZones() }
    }

    @Test
    fun `syncFromServer applies when remote version is newer`() = runTest {
        coEvery { zoneApi.fetchVersion() } returns
            VersionResponse("2026-07-20T02:10:00Z", "serverhash", null, 1)
        every { settingsRepository.cachedZoneHash } returns flowOf("localhash")
        every { settingsRepository.cachedZoneVersion } returns flowOf("2026-07-17T11:51:47Z")
        coEvery { zoneApi.fetchZones() } returns
            ZonesResponse("2026-07-20T02:10:00Z", "serverhash", listOf(testZone))

        val result = repository.syncFromServer()

        assertEquals(SyncResult.Updated, result)
        coVerify { zoneDao.replaceAll(any()) }
        coVerify { settingsRepository.setCachedZoneVersion("2026-07-20T02:10:00Z") }
    }

    @Test
    fun `syncFromServer applies when cached version is legacy`() = runTest {
        // Pre-recency installs cached "" or non-timestamp versions — not
        // comparable, so the pre-ISSUE-011 hash-only behavior applies.
        coEvery { zoneApi.fetchVersion() } returns
            VersionResponse("2026-07-13T06:10:40Z", "serverhash", null, 1)
        every { settingsRepository.cachedZoneHash } returns flowOf("localhash")
        every { settingsRepository.cachedZoneVersion } returns flowOf("v1")
        coEvery { zoneApi.fetchZones() } returns
            ZonesResponse("2026-07-13T06:10:40Z", "serverhash", listOf(testZone))

        val result = repository.syncFromServer()

        assertEquals(SyncResult.Updated, result)
        coVerify { zoneApi.fetchZones() }
    }
}
