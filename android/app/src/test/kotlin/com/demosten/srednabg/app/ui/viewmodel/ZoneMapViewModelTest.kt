// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.viewmodel

import app.cash.turbine.test
import com.demosten.srednabg.app.data.MapRepository
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.core.MapTheme
import com.demosten.srednabg.core.MapThemeMode
import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import io.mockk.every
import io.mockk.mockk
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
class ZoneMapViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var zoneRepository: ZoneRepository
    private lateinit var settingsRepository: SettingsRepository
    private lateinit var mapRepository: MapRepository

    @BeforeEach
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
    }

    @AfterEach
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `empty list is default state`() {
        zoneRepository = mockk()
        every { zoneRepository.zones } returns flowOf(emptyList())

        settingsRepository = mockk()
        every { settingsRepository.mapHeadingUp } returns flowOf(false)
        every { settingsRepository.mapThemeMode } returns flowOf(MapThemeMode.AUTO)
        every { settingsRepository.mapZoomOverride } returns flowOf<Float?>(null)
        every { settingsRepository.debugMaxSpeedOverride } returns flowOf<Int?>(null)
        every { settingsRepository.vehicleType } returns flowOf("car")

        mapRepository = mockk()
        every { mapRepository.localStyleUri(MapTheme.LIGHT) } returns "file:///dev/null/style-light.json"
        every { mapRepository.localStyleUri(MapTheme.DARK) } returns "file:///dev/null/style-dark.json"

        val viewModel = ZoneMapViewModel(zoneRepository, settingsRepository, mapRepository)

        assertEquals(emptyList<Zone>(), viewModel.zones.value)
    }

    @Test
    fun `follow mode is held in the view model so it survives tab switches`() {
        // Regression: follow mode used to live in ZoneMapScreen's local Compose
        // state, so leaving the Map tab (NavHost disposes the screen) silently
        // reset it to off. Holding it in the VM — retained across the tab's
        // back-stack entry — keeps an enabled follow alive on return.
        zoneRepository = mockk()
        every { zoneRepository.zones } returns flowOf(emptyList())

        settingsRepository = mockk()
        every { settingsRepository.mapHeadingUp } returns flowOf(false)
        every { settingsRepository.mapThemeMode } returns flowOf(MapThemeMode.AUTO)
        every { settingsRepository.mapZoomOverride } returns flowOf<Float?>(null)
        every { settingsRepository.debugMaxSpeedOverride } returns flowOf<Int?>(null)
        every { settingsRepository.vehicleType } returns flowOf("car")

        mapRepository = mockk()
        every { mapRepository.localStyleUri(MapTheme.LIGHT) } returns "file:///dev/null/style-light.json"
        every { mapRepository.localStyleUri(MapTheme.DARK) } returns "file:///dev/null/style-dark.json"

        val viewModel = ZoneMapViewModel(zoneRepository, settingsRepository, mapRepository)

        assertEquals(false, viewModel.isFollowing.value)
        viewModel.setFollowing(true)
        assertEquals(true, viewModel.isFollowing.value)
        viewModel.setFollowing(false)
        assertEquals(false, viewModel.isFollowing.value)
    }

    @Test
    fun `zones state reflects repository flow`() = runTest {
        val testZones = listOf(
            Zone(
                id = "test-1",
                road = "Test Road",
                roadLatin = null,
                direction = "east",
                description = "Test",
                start = ZoneEndpoint(lat = 42.0, lng = 23.0),
                end = ZoneEndpoint(lat = 42.1, lng = 23.1),
                distanceM = 5000,
                speedLimits = SpeedLimits(car = 120, truck = 80, bus = 90),
                centerline = listOf(listOf(42.0, 23.0), listOf(42.1, 23.1)),
                source = "test",
                lastVerified = "2026-04-12",
            ),
        )

        zoneRepository = mockk()
        every { zoneRepository.zones } returns flowOf(testZones)

        settingsRepository = mockk()
        every { settingsRepository.mapHeadingUp } returns flowOf(false)
        every { settingsRepository.mapThemeMode } returns flowOf(MapThemeMode.AUTO)
        every { settingsRepository.mapZoomOverride } returns flowOf<Float?>(null)
        every { settingsRepository.debugMaxSpeedOverride } returns flowOf<Int?>(null)
        every { settingsRepository.vehicleType } returns flowOf("car")

        mapRepository = mockk()
        every { mapRepository.localStyleUri(MapTheme.LIGHT) } returns "file:///dev/null/style-light.json"
        every { mapRepository.localStyleUri(MapTheme.DARK) } returns "file:///dev/null/style-dark.json"

        val viewModel = ZoneMapViewModel(zoneRepository, settingsRepository, mapRepository)

        viewModel.zones.test {
            val zones = awaitItem()
            if (zones.isEmpty()) {
                // Initial empty value from stateIn — wait for the real emission
                val actual = awaitItem()
                assertEquals(1, actual.size)
                assertEquals("test-1", actual[0].id)
            } else {
                assertEquals(1, zones.size)
                assertEquals("test-1", zones[0].id)
            }
        }
    }
}
