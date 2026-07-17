// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.viewmodel

import app.cash.turbine.test
import com.demosten.srednabg.app.data.FakeZoneTraversalDao
import com.demosten.srednabg.app.data.HistoryRepository
import com.demosten.srednabg.app.data.MapHighlightStore
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.data.traversalEntity
import com.demosten.srednabg.app.service.LocationTrackingService
import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import com.google.gson.Gson
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

@OptIn(ExperimentalCoroutinesApi::class)
class HistoryViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private val dao = FakeZoneTraversalDao()
    private lateinit var settingsRepository: SettingsRepository
    private lateinit var zoneRepository: ZoneRepository
    private lateinit var mapHighlightStore: MapHighlightStore
    private lateinit var viewModel: HistoryViewModel

    // Anchor timestamps to a fixed calendar day so the day-grouping assertions
    // don't depend on the machine's clock. day1Noon + dayMs lands on the next
    // calendar day in any real timezone (all are within ±14 h of UTC).
    private val dayMs = 24L * 60 * 60 * 1000
    // 2026-06-15 12:00 local, plus offset so it's midday regardless of zone.
    private val day1Noon = 1_781_000_000_000L

    @BeforeEach
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        settingsRepository = mockk(relaxed = true)
        every { settingsRepository.historyRetention } returns flowOf("3months")
        zoneRepository = mockk(relaxed = true)
        every { zoneRepository.zones } returns flowOf(emptyList())
        mapHighlightStore = MapHighlightStore()
        viewModel = newViewModel()
    }

    private fun newViewModel() = HistoryViewModel(
        HistoryRepository(dao),
        settingsRepository,
        zoneRepository,
        mapHighlightStore,
        Gson(),
    )

    @AfterEach
    fun tearDown() {
        Dispatchers.resetMain()
        trackingFlow().value = false
    }

    /**
     * `canShowOnMap` gates on the process-global
     * `LocationTrackingService.isTracking`; its backing flow is private (only
     * the real service flips it), so the tracking case reaches the instance
     * through reflection rather than widening production visibility for a test.
     */
    @Suppress("UNCHECKED_CAST")
    private fun trackingFlow(): MutableStateFlow<Boolean> {
        val field = LocationTrackingService::class.java.getDeclaredField("_isTracking")
        field.isAccessible = true
        return field.get(null) as MutableStateFlow<Boolean>
    }

    /** A catalog zone whose id matches [traversalEntity]'s `zone-<id>`. */
    private fun catalogZone(id: String) = Zone(
        id = id,
        road = "АМ Тракия",
        roadLatin = "Trakiya",
        direction = "east",
        description = "test zone",
        start = ZoneEndpoint(lat = 42.0, lng = 24.0),
        end = ZoneEndpoint(lat = 42.0, lng = 24.2),
        distanceM = 19160,
        speedLimits = SpeedLimits(car = 140, truck = 100, bus = 100),
        centerline = listOf(listOf(42.0, 24.0), listOf(42.0, 24.2)),
        source = "test",
        lastVerified = "2026-01-01",
    )

    @Test
    fun `records on the same day group under one header, most recent first`() = runTest {
        dao.insert(traversalEntity("early", exitTimeMs = day1Noon))
        dao.insert(traversalEntity("late", exitTimeMs = day1Noon + 3 * 60 * 60 * 1000))

        viewModel.days.test {
            var groups = awaitItem()
            while (groups.sumOf { it.items.size } < 2) groups = awaitItem()
            assertEquals(1, groups.size)
            assertEquals(listOf("late", "early"), groups.single().items.map { it.id })
        }
    }

    @Test
    fun `records on different days form separate groups, newest day first`() = runTest {
        dao.insert(traversalEntity("today", exitTimeMs = day1Noon + dayMs))
        dao.insert(traversalEntity("yesterday", exitTimeMs = day1Noon))

        viewModel.days.test {
            var groups = awaitItem()
            while (groups.size < 2) groups = awaitItem()
            assertEquals(2, groups.size)
            assertTrue(groups[0].epochDay > groups[1].epochDay)
            assertEquals("today", groups[0].items.single().id)
            assertEquals("yesterday", groups[1].items.single().id)
        }
    }

    @Test
    fun `uiState reflects the disabled flag from retention none`() = runTest {
        every { settingsRepository.historyRetention } returns flowOf("none")
        viewModel = newViewModel()
        viewModel.uiState.test {
            var state = awaitItem()
            while (!state.recordingDisabled) state = awaitItem()
            assertTrue(state.recordingDisabled)
        }
    }

    @Test
    fun `uiState not disabled for a real retention window`() = runTest {
        viewModel.uiState.test {
            assertFalse(awaitItem().recordingDisabled)
        }
    }

    @Test
    fun `loadDetail hydrates the selected record with parsed samples`() = runTest {
        dao.insert(traversalEntity("a", exitTimeMs = day1Noon))
        viewModel.loadDetail("a")
        viewModel.detailState.test {
            var state = awaitItem()
            while (state !is HistoryDetailUiState.Loaded) state = awaitItem()
            assertEquals("a", state.detail.id)
        }
    }

    @Test
    fun `loadDetail reports NotFound for an unknown id`() = runTest {
        viewModel.loadDetail("missing")
        viewModel.detailState.test {
            var state = awaitItem()
            while (state !is HistoryDetailUiState.NotFound) state = awaitItem()
            assertTrue(state is HistoryDetailUiState.NotFound)
        }
    }

    @Test
    fun `canShowOnMap is true once the detail loads and its zone resolves`() = runTest {
        dao.insert(traversalEntity("a", exitTimeMs = day1Noon))
        every { zoneRepository.zones } returns flowOf(listOf(catalogZone("zone-a")))
        viewModel = newViewModel()
        viewModel.loadDetail("a")
        viewModel.canShowOnMap.test {
            var enabled = awaitItem()
            while (!enabled) enabled = awaitItem()
            assertTrue(enabled)
        }
    }

    @Test
    fun `canShowOnMap stays false when the zone is gone from the catalog`() = runTest {
        dao.insert(traversalEntity("a", exitTimeMs = day1Noon))
        every { zoneRepository.zones } returns flowOf(listOf(catalogZone("zone-other")))
        viewModel = newViewModel()
        viewModel.loadDetail("a")
        viewModel.detailState.test {
            var state = awaitItem()
            while (state !is HistoryDetailUiState.Loaded) state = awaitItem()
        }
        viewModel.canShowOnMap.test {
            assertFalse(awaitItem())
        }
    }

    @Test
    fun `canShowOnMap stays false while tracking is active`() = runTest {
        dao.insert(traversalEntity("a", exitTimeMs = day1Noon))
        every { zoneRepository.zones } returns flowOf(listOf(catalogZone("zone-a")))
        trackingFlow().value = true
        viewModel = newViewModel()
        viewModel.loadDetail("a")
        viewModel.detailState.test {
            var state = awaitItem()
            while (state !is HistoryDetailUiState.Loaded) state = awaitItem()
        }
        viewModel.canShowOnMap.test {
            assertFalse(awaitItem())
        }
    }

    @Test
    fun `showOnMap publishes the record's zone and verdict`() = runTest {
        dao.insert(traversalEntity("a", exitTimeMs = day1Noon, isOverLimit = true))
        viewModel.loadDetail("a")
        viewModel.detailState.test {
            var state = awaitItem()
            while (state !is HistoryDetailUiState.Loaded) state = awaitItem()
        }
        viewModel.showOnMap()
        val highlight = mapHighlightStore.highlight.value
        assertEquals("zone-a", highlight?.zoneId)
        assertEquals(true, highlight?.isOverLimit)
    }
}
