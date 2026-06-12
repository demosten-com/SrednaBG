// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.util

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.time.ZoneId
import java.util.Locale

class ZoneDataFormatTest {

    @Test
    fun `prefixed hash drops sha256 prefix and takes first 16 chars`() {
        assertEquals(
            "e344717a5262a595",
            shortZoneHash("sha256:e344717a5262a59526484fa9f48e68173e84939498f96535997e1c7f8a38644b"),
        )
    }

    @Test
    fun `unprefixed hash takes first 16 chars`() {
        assertEquals(
            "e344717a5262a595",
            shortZoneHash("e344717a5262a59526484fa9f48e68173e84939498f96535997e1c7f8a38644b"),
        )
    }

    @Test
    fun `hash shorter than 16 chars passes through`() {
        assertEquals("abc123", shortZoneHash("abc123"))
    }

    @Test
    fun `null hash renders as dash`() {
        assertEquals(DASH_PLACEHOLDER, shortZoneHash(null))
    }

    @Test
    fun `empty hash renders as dash`() {
        assertEquals(DASH_PLACEHOLDER, shortZoneHash(""))
    }

    @Test
    fun `bare prefix renders as dash`() {
        assertEquals(DASH_PLACEHOLDER, shortZoneHash("sha256:"))
    }

    @Test
    fun `version formats in locale short style in given zone`() {
        assertEquals(
            "6/11/26, 5:32 AM",
            formatZoneVersion("2026-06-11T05:32:40Z", Locale.US, ZoneId.of("UTC")).normalizeSpaces(),
        )
    }

    @Test
    fun `version converts to target time zone`() {
        assertEquals(
            "6/11/26, 8:32 AM",
            formatZoneVersion("2026-06-11T05:32:40Z", Locale.US, ZoneId.of("Europe/Sofia")).normalizeSpaces(),
        )
    }

    @Test
    fun `null version renders as dash`() {
        assertEquals(DASH_PLACEHOLDER, formatZoneVersion(null))
    }

    @Test
    fun `blank version renders as dash`() {
        assertEquals(DASH_PLACEHOLDER, formatZoneVersion(""))
    }

    @Test
    fun `unparseable version renders as dash`() {
        assertEquals(DASH_PLACEHOLDER, formatZoneVersion("not-a-date"))
    }
}

// CLDR emits a narrow no-break space (U+202F) before AM/PM on newer JDKs.
private fun String.normalizeSpaces(): String = replace(' ', ' ').replace(' ', ' ')
