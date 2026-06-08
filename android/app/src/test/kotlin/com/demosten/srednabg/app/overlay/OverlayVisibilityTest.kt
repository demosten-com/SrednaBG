// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.overlay

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class OverlayVisibilityTest {

    @Test
    fun `visible only when all four inputs hold`() {
        assertTrue(
            shouldShowOverlay(
                enabled = true,
                canDrawOverlays = true,
                tracking = true,
                appInBackground = true,
            ),
        )
    }

    @Test
    fun `hidden when setting is off`() {
        assertFalse(
            shouldShowOverlay(
                enabled = false,
                canDrawOverlays = true,
                tracking = true,
                appInBackground = true,
            ),
        )
    }

    @Test
    fun `hidden without the overlay permission`() {
        assertFalse(
            shouldShowOverlay(
                enabled = true,
                canDrawOverlays = false,
                tracking = true,
                appInBackground = true,
            ),
        )
    }

    @Test
    fun `hidden when not tracking`() {
        assertFalse(
            shouldShowOverlay(
                enabled = true,
                canDrawOverlays = true,
                tracking = false,
                appInBackground = true,
            ),
        )
    }

    @Test
    fun `hidden while our own app is in the foreground`() {
        assertFalse(
            shouldShowOverlay(
                enabled = true,
                canDrawOverlays = true,
                tracking = true,
                appInBackground = false,
            ),
        )
    }
}
