// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.viewmodel

import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.data.ZoneSyncScheduler
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var settingsRepository: SettingsRepository
    private lateinit var zoneRepository: ZoneRepository
    private lateinit var zoneSyncScheduler: ZoneSyncScheduler
    private lateinit var viewModel: SettingsViewModel

    @BeforeEach
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        settingsRepository = mockk(relaxed = true)
        zoneRepository = mockk(relaxed = true)
        zoneSyncScheduler = mockk(relaxed = true)

        every { settingsRepository.voiceEnabled } returns flowOf(true)
        every { settingsRepository.periodicVoiceUpdates } returns flowOf(true)
        every { settingsRepository.announceOnlyWhenOver } returns flowOf(true)
        every { settingsRepository.appLanguage } returns flowOf("system")
        every { settingsRepository.vehicleType } returns flowOf("car")
        every { settingsRepository.historyRetention } returns flowOf("3months")

        viewModel = SettingsViewModel(settingsRepository, zoneRepository, zoneSyncScheduler)
    }

    @AfterEach
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `initial state reflects repository defaults`() {
        assertEquals(true, viewModel.voiceEnabled.value)
        assertEquals(true, viewModel.periodicVoiceUpdates.value)
        assertEquals(true, viewModel.announceOnlyWhenOver.value)
        assertEquals("system", viewModel.appLanguage.value)
        assertEquals("car", viewModel.vehicleType.value)
    }

    @Test
    fun `setVoiceEnabled delegates to repository`() = runTest {
        viewModel.setVoiceEnabled(false)
        coVerify { settingsRepository.setVoiceEnabled(false) }
    }

    @Test
    fun `historyRetention reflects repository default`() {
        assertEquals("3months", viewModel.historyRetention.value)
    }

    @Test
    fun `setHistoryRetention delegates to repository`() = runTest {
        viewModel.setHistoryRetention("none")
        coVerify { settingsRepository.setHistoryRetention("none") }
    }

    @Test
    fun `setPeriodicVoiceUpdates delegates to repository`() = runTest {
        viewModel.setPeriodicVoiceUpdates(false)
        coVerify { settingsRepository.setPeriodicVoiceUpdates(false) }
    }

    @Test
    fun `setAnnounceOnlyWhenOver delegates to repository`() = runTest {
        viewModel.setAnnounceOnlyWhenOver(false)
        coVerify { settingsRepository.setAnnounceOnlyWhenOver(false) }
    }

    @Test
    fun `setAppLanguage delegates to repository`() = runTest {
        viewModel.setAppLanguage("en")
        coVerify { settingsRepository.setAppLanguage("en") }
    }

    @Test
    fun `setVehicleType delegates to repository`() = runTest {
        viewModel.setVehicleType("truck")
        coVerify { settingsRepository.setVehicleType("truck") }
    }

    @Test
    fun `syncNow delegates to zone repository`() = runTest {
        viewModel.syncNow()
        coVerify { zoneRepository.syncFromServer() }
    }

    @Test
    fun `setZoneSyncEnabled true persists and enables the scheduler`() = runTest {
        viewModel.setZoneSyncEnabled(true)
        coVerify { settingsRepository.setZoneSyncEnabled(true) }
        verify { zoneSyncScheduler.enable() }
    }

    @Test
    fun `setZoneSyncEnabled false persists and disables the scheduler`() = runTest {
        viewModel.setZoneSyncEnabled(false)
        coVerify { settingsRepository.setZoneSyncEnabled(false) }
        verify { zoneSyncScheduler.disable() }
    }
}
