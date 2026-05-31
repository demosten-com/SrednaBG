// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app (aosp flavor unit tests)

package com.demosten.srednabg.app.service

import android.content.Context
import android.location.LocationManager
import android.util.Log
import io.mockk.every
import io.mockk.mockk
import io.mockk.mockkStatic
import io.mockk.unmockkStatic
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

/**
 * The aosp flavor must never build a GMS-backed source — it has no Play
 * Services dependency. This guards against an accidental re-link of
 * FusedLocationProvider into the FOSS / F-Droid build.
 */
class AospLocationSourceTest {

    @BeforeEach
    fun setUp() {
        mockkStatic(Log::class)
        every { Log.d(any(), any()) } returns 0
    }

    @AfterEach
    fun tearDown() {
        unmockkStatic(Log::class)
    }

    @Test
    fun `aosp factory always builds a SystemLocationSource`() {
        val lm = mockk<LocationManager>(relaxed = true)
        val context = mockk<Context>()
        every { context.getSystemService(Context.LOCATION_SERVICE) } returns lm

        val source = createLocationSource(context) { /* no-op listener */ }

        assertTrue(
            source is SystemLocationSource,
            "aosp createLocationSource must return a SystemLocationSource, got ${source::class.simpleName}",
        )
    }
}
