// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import app.cash.turbine.test
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsRepositoryTest {

    @TempDir
    lateinit var tmpDir: File

    private lateinit var dataStore: DataStore<Preferences>
    private lateinit var repository: SettingsRepository
    private val testDispatcher = UnconfinedTestDispatcher()
    private val testScope = TestScope(testDispatcher + Job())

    @BeforeEach
    fun setUp() {
        dataStore = PreferenceDataStoreFactory.create(
            scope = testScope,
            produceFile = { File(tmpDir, "test_prefs.preferences_pb") },
        )
        repository = SettingsRepository(dataStore)
    }

    @Test
    fun `default voiceEnabled is true`() = runTest {
        repository.voiceEnabled.test {
            assertEquals(true, awaitItem())
        }
    }

    @Test
    fun `default appLanguage is system`() = runTest {
        repository.appLanguage.test {
            assertEquals("system", awaitItem())
        }
    }

    @Test
    fun `default periodicVoiceUpdates is true`() = runTest {
        repository.periodicVoiceUpdates.test {
            assertEquals(true, awaitItem())
        }
    }

    @Test
    fun `setPeriodicVoiceUpdates persists and emits new value`() = runTest {
        repository.periodicVoiceUpdates.test {
            assertEquals(true, awaitItem())
            repository.setPeriodicVoiceUpdates(false)
            assertEquals(false, awaitItem())
        }
    }

    @Test
    fun `default announceOnlyWhenOver is true`() = runTest {
        repository.announceOnlyWhenOver.test {
            assertEquals(true, awaitItem())
        }
    }

    @Test
    fun `setAnnounceOnlyWhenOver persists and emits new value`() = runTest {
        repository.announceOnlyWhenOver.test {
            assertEquals(true, awaitItem())
            repository.setAnnounceOnlyWhenOver(false)
            assertEquals(false, awaitItem())
        }
    }

    @Test
    fun `voiceLanguage follows appLanguage when explicit`() = runTest {
        repository.setAppLanguage("en")
        repository.voiceLanguage.test {
            assertEquals("en", awaitItem())
        }
        repository.setAppLanguage("bg")
        repository.voiceLanguage.test {
            assertEquals("bg", awaitItem())
        }
    }

    @Test
    fun `default vehicleType is car`() = runTest {
        repository.vehicleType.test {
            assertEquals("car", awaitItem())
        }
    }

    @Test
    fun `setVoiceEnabled persists and emits new value`() = runTest {
        repository.voiceEnabled.test {
            assertEquals(true, awaitItem())
            repository.setVoiceEnabled(false)
            assertEquals(false, awaitItem())
        }
    }

    @Test
    fun `setAppLanguage persists and emits new value`() = runTest {
        repository.appLanguage.test {
            assertEquals("system", awaitItem())
            repository.setAppLanguage("en")
            assertEquals("en", awaitItem())
        }
    }

    @Test
    fun `setVehicleType persists and emits new value`() = runTest {
        repository.vehicleType.test {
            assertEquals("car", awaitItem())
            repository.setVehicleType("truck")
            assertEquals("truck", awaitItem())
        }
    }

    @Test
    fun `setCachedZoneHash persists and emits new value`() = runTest {
        repository.cachedZoneHash.test {
            assertEquals("", awaitItem())
            repository.setCachedZoneHash("abc123")
            assertEquals("abc123", awaitItem())
        }
    }

    @Test
    fun `default historyRetention is 3months`() = runTest {
        repository.historyRetention.test {
            assertEquals(SettingsRepository.DEFAULT_HISTORY_RETENTION, awaitItem())
        }
    }

    @Test
    fun `setHistoryRetention persists and emits new value`() = runTest {
        repository.historyRetention.test {
            assertEquals("3months", awaitItem())
            repository.setHistoryRetention("none")
            assertEquals("none", awaitItem())
        }
    }

    @Test
    fun `default zoneSyncEnabled is true`() = runTest {
        repository.zoneSyncEnabled.test {
            assertEquals(SettingsRepository.DEFAULT_ZONE_SYNC_ENABLED, awaitItem())
        }
    }

    @Test
    fun `setZoneSyncEnabled persists and emits new value`() = runTest {
        repository.zoneSyncEnabled.test {
            assertEquals(true, awaitItem())
            repository.setZoneSyncEnabled(false)
            assertEquals(false, awaitItem())
        }
    }
}
