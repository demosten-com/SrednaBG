// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.viewmodel

import android.content.Context
import com.demosten.srednabg.app.data.MapRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.permissions.PermissionRepository
import com.demosten.srednabg.app.permissions.PermissionState
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

/**
 * Pure-logic checks for the permission gate inside `startTracking`. We can't
 * run a real foreground service in JVM tests, so we count interactions on a
 * mocked `Context` to confirm the gate either does or doesn't dispatch the
 * service-start intent.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var zoneRepository: ZoneRepository
    private lateinit var mapRepository: MapRepository
    private lateinit var permissionRepository: PermissionRepository
    private lateinit var context: Context
    private val permissionFlow = MutableStateFlow(PermissionState())

    @BeforeEach
    fun setUp() {
        Dispatchers.setMain(testDispatcher)

        zoneRepository = mockk(relaxed = true)
        every { zoneRepository.zones } returns flowOf(emptyList())

        mapRepository = mockk(relaxed = true)

        permissionRepository = mockk()
        every { permissionRepository.state } returns permissionFlow
        every { permissionRepository.refresh() } answers {}

        context = mockk(relaxed = true) {
            every { packageName } returns "com.demosten.srednabg"
        }
    }

    @AfterEach
    fun tearDown() {
        Dispatchers.resetMain()
    }

    /**
     * In JVM unit tests, `Build.VERSION.SDK_INT` is `0`, which makes
     * `ContextCompat.startForegroundService` route to plain `startService`
     * instead of the API-26+ overload. Either call satisfies the gate's
     * intent — that the service was dispatched — so we accept both.
     */
    private fun verifyServiceStarted() {
        verify(exactly = 1) { context.startService(any()) }
    }

    private fun verifyServiceNotStarted() {
        verify(exactly = 0) { context.startForegroundService(any()) }
        verify(exactly = 0) { context.startService(any()) }
    }

    private fun viewModelWith(state: PermissionState): HomeViewModel {
        permissionFlow.value = state
        return HomeViewModel(zoneRepository, mapRepository, permissionRepository, context)
    }

    @Test
    fun `startTracking refuses when fine location is missing`() {
        val vm = viewModelWith(
            PermissionState(
                fineLocationGranted = false,
                backgroundLocationGranted = false,
                notificationGranted = true,
                ignoringBatteryOptimizations = true,
            ),
        )
        vm.startTracking()
        verifyServiceNotStarted()
    }

    @Test
    fun `startTracking refuses when background location is missing`() {
        // Most likely real-world failure mode: user granted "While using" but
        // declined background. iOS equivalent: granted When-In-Use, declined
        // the Always upgrade. Either way, GPS dies on screen lock.
        val vm = viewModelWith(
            PermissionState(
                fineLocationGranted = true,
                backgroundLocationGranted = false,
                notificationGranted = true,
                ignoringBatteryOptimizations = true,
            ),
        )
        vm.startTracking()
        verifyServiceNotStarted()
    }

    @Test
    fun `startTracking proceeds without POST_NOTIFICATIONS`() {
        // Notification permission is intentionally NOT part of the gate. The
        // foreground service still runs without it; the missing FGS
        // notification is a reliability risk surfaced as an in-app advisory
        // card, not a blocker. Forcing it into the gate stranded users who
        // declined the OS prompt with no in-app way to start tracking.
        val vm = viewModelWith(
            PermissionState(
                fineLocationGranted = true,
                backgroundLocationGranted = true,
                notificationGranted = false,
                ignoringBatteryOptimizations = true,
            ),
        )
        vm.startTracking()
        verifyServiceStarted()
    }

    @Test
    fun `startTracking proceeds once both location permissions are granted`() {
        // Battery optimization is also intentionally NOT part of the gate —
        // it's a best-effort nudge, not a hard requirement. The OS will still
        // service the foreground intent and most devices respect it.
        val vm = viewModelWith(
            PermissionState(
                fineLocationGranted = true,
                backgroundLocationGranted = true,
                notificationGranted = true,
                ignoringBatteryOptimizations = false,
            ),
        )
        vm.startTracking()
        verifyServiceStarted()
    }

    @Test
    fun `refreshPermissions delegates to repository`() {
        val vm = viewModelWith(PermissionState())
        vm.refreshPermissions()
        verify(exactly = 1) { permissionRepository.refresh() }
    }

    @Test
    fun `permissionState exposes repository flow`() {
        val state = PermissionState(fineLocationGranted = true)
        val vm = viewModelWith(state)
        assertEquals(state, vm.permissionState.value)
    }
}
