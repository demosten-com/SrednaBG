// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.util

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class SpeedFormatTest {

    @Test
    fun `null renders as dash`() {
        val value: Double? = null
        assertEquals("--", value.orDash())
    }

    @Test
    fun `NaN renders as dash`() {
        assertEquals("--", Double.NaN.orDash())
    }

    @Test
    fun `positive infinity renders as dash`() {
        assertEquals("--", Double.POSITIVE_INFINITY.orDash())
    }

    @Test
    fun `negative infinity renders as dash`() {
        assertEquals("--", Double.NEGATIVE_INFINITY.orDash())
    }

    @Test
    fun `whole number formats with default integer format`() {
        assertEquals("87", 87.0.orDash())
    }

    @Test
    fun `fractional number truncates to integer with default format`() {
        assertEquals("87", 87.6.orDash())
    }

    @Test
    fun `custom float format preserves decimals`() {
        assertEquals("87.6", 87.6.orDash("%.1f"))
    }
}
