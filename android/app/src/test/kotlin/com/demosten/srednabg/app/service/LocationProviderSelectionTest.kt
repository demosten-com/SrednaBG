// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import android.location.LocationManager
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/**
 * SrednaBG is GPS-only: [chooseLocationProviders] must never register the
 * cell/wifi NETWORK provider (it's 100 m–2 km off and caused wild speed spikes,
 * zone flapping, and inflated averages when interleaved with GPS fixes). When
 * GPS is unavailable it returns empty rather than falling back to a coarse
 * provider — an imprecise fix is worse than none. This guards against
 * re-introducing the dual-provider registration.
 */
class LocationProviderSelectionTest {

    @Test
    fun `picks GPS only when both GPS and NETWORK are enabled`() {
        val result = chooseLocationProviders(
            listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER),
        )
        assertEquals(listOf(LocationManager.GPS_PROVIDER), result)
    }

    @Test
    fun `picks GPS when only GPS is enabled`() {
        val result = chooseLocationProviders(listOf(LocationManager.GPS_PROVIDER))
        assertEquals(listOf(LocationManager.GPS_PROVIDER), result)
    }

    @Test
    fun `returns empty when only NETWORK is enabled (no coarse fallback)`() {
        val result = chooseLocationProviders(
            listOf(LocationManager.NETWORK_PROVIDER, LocationManager.PASSIVE_PROVIDER),
        )
        assertEquals(emptyList<String>(), result)
    }

    @Test
    fun `returns empty when no providers are enabled`() {
        val result = chooseLocationProviders(emptyList())
        assertEquals(emptyList<String>(), result)
    }
}
