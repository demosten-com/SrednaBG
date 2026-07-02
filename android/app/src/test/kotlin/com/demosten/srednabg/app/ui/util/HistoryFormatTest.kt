// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.util

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class HistoryFormatTest {

    @Test
    fun `known compass directions map to their canonical key`() {
        assertEquals("east", directionKey("east"))
        assertEquals("west", directionKey("west"))
        assertEquals("north", directionKey("north"))
        assertEquals("south", directionKey("south"))
    }

    @Test
    fun `direction key is case- and whitespace-insensitive`() {
        assertEquals("east", directionKey(" East "))
        assertEquals("south", directionKey("SOUTH"))
    }

    @Test
    fun `unknown direction has no key so the UI renders nothing`() {
        assertNull(directionKey(""))
        assertNull(directionKey("northeast"))
        assertNull(directionKey("изток"))
    }
}
